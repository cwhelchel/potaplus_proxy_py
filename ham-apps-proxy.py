'''
    ham-apps-proxy PYTHON: a replacement for the ham-apps-proxy by David 
    Westbrook (K2DW).  

    Assume that everything here will blow up in some way. This is provided for 
    entertainment purposes only (you can laugh at my code). My setup is a 
    Windows laptop running Log4om 2 and a Xiegu G90. It's tested and works to
    log from the UI and to QSY my rig. I've also tested N3FJP's aclog and it
    seems to work but requires a front end change

    -Cainan KQ4DAP
'''

import os.path
import datetime
import argparse
import time
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import socket
import win32com.client

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*']
)

# this may take some time so we do it first
# omnirig = win32com.client.Dispatch("{0839E8C6-ED30-4950-8087-966F970F0CAE}")

# try this: the app (via omni-rig) holds the com port open
omnirig = win32com.client.gencache.EnsureDispatch("OmniRig.OmniRigX")

'''
methods of IRigX as registered on windows:

[Guid("501a2858-3331-467a-837a-989fdedacc7d")]
interface IOmniRigX
{
   /* Properties */
   int InterfaceVersion { get; }
   int SoftwareVersion { get; }
   RigX Rig1 { get; }
   RigX Rig2 { get; }
   bool DialogVisible { get; set; }
}

[Guid("d30a7e51-5862-45b7-bffa-6415917da0cf")]
interface IRigX
{
   /* Methods */
   bool IsParamReadable(RigParamX Param);
   bool IsParamWriteable(RigParamX Param);
   void ClearRit();
   void SetSimplexMode(int Freq);
   void SetSplitMode(int RxFreq, int TxFreq);
   int FrequencyOfTone(int Tone);
   void SendCustomCommand(object Command, int ReplyLength, object ReplyEnd);
   int GetRxFrequency();
   int GetTxFrequency();
   /* Properties */
   string RigType { get; }
   int ReadableParams { get; }
   int WriteableParams { get; }
   RigStatusX Status { get; }
   string StatusStr { get; }
   int Freq { get; set; }
   int FreqA { get; set; }
   int FreqB { get; set; }
   int RitOffset { get; set; }
   int Pitch { get; set; }
   RigParamX Vfo { get; set; }
   RigParamX Split { get; set; }
   RigParamX Rit { get; set; }
   RigParamX Xit { get; set; }
   RigParamX Tx { get; set; }
   RigParamX Mode { get; set; }
   PortBits PortBits { get; }
}
'''

print(omnirig)
print(f"PM_FREQ: {omnirig.Rig1.IsParamWriteable(0x00000002)}")
print(f"PM_FREQA: {omnirig.Rig1.IsParamWriteable(0x00000004)}")
print(f"PM_FREQB: {omnirig.Rig1.IsParamWriteable(0x00000008)}")
print(f"PM_RITOFFSET: {omnirig.Rig1.IsParamWriteable(0x00000020)}")
print(f"PM_RIT0: {omnirig.Rig1.IsParamWriteable(0x00000040)}")
print(f"PM_RITON: {omnirig.Rig1.IsParamWriteable(0x00020000)}")
print(f"PM_RITOFF: {omnirig.Rig1.IsParamWriteable(0x00040000)}")
print(f"PM_CW_U: {omnirig.Rig1.IsParamWriteable(0x00800000)}")
print(f"PM_CW_L: {omnirig.Rig1.IsParamWriteable(0x01000000)}")
print(f"PM_SSB_U: {omnirig.Rig1.IsParamWriteable(0x02000000)}")
print(f"PM_SSB_L: {omnirig.Rig1.IsParamWriteable(0x04000000)}")

print(f"PM_RITON: {omnirig.Rig1.IsParamWriteable(0x0002_0000)}")
print(f"PM_RITOFF: {omnirig.Rig1.IsParamWriteable(0x0004_0000)}")
print(f"PM_XITON: {omnirig.Rig1.IsParamWriteable(0x0008_0000)}")
print(f"PM_XITOFF: {omnirig.Rig1.IsParamWriteable(0x0010_0000)}")

VER = "0.0.7"
LOG4OM_HOST = "localhost"
LOG4OM_PORT = 2239
ACLOG_HOST = "localhost"
ACLOG_PORT = 1100
BACKUP_LOG_FN = "proxy_log.adi"

print("---------------------------------")
print(f"POTA Plus Python Proxy v: {VER}")
print(f"starting...")


config = {
    'cw_rit': 0,  # offset in HZ, if nonzero is added to freq
    'cw_xit': False,  # true to turn on XIT for CW mode and OFF for others
    'g90': False
}


@app.get("/", response_class=HTMLResponse)
async def root():
    return f"""
    <html>
        <head>
            <title>ham-apps-proxy PY</title>
        </head>
        <body>
            <h1>ham-apps-proxy PYTHON</h1>
            <p>
            Welcome to ham-apps-proxy Python webapi written by <a href="https://www.qrz.com/db/KQ4DAP">KQ4DAP</a>.
            </p>
            <p>Version is: <code>{VER}</code> </p>
        </body>
    </html>
    """


@app.get("/version")
async def version():
    return {"version": VER}


'''
The various endpoints should take the following query parameters at a minimum
http://localhost:8073/log4om/log?
    CALL=W1AW&
    RST_SENT=599&
    RST_RCVD=599&
    FREQ=1.84027&     <adif wants MHz>
    FREQ_RX=1.84027&  <adif wants MHz>
    BAND=160M&  
    MODE=CW&
    QSO_DATE=20170515&
    TIME_ON=210700&  <presumable UTC>
    STATION_CALLSIGN=AA6YQ&
    TX_PWR=1500&
    RX_PWR=0

Others adif fields maybe added by the user (SIG=POTA or SIG_INFO=K-7465) in the
extension options.

Also __host and __port may be present in the query parameters, these are the 
endpoint data destination for the adif message. Set by user in options.
'''


@app.get("/log4om/log")
async def log4om_log(request: Request):
    '''Log QSO using Log4OM via ADIF message.
    
    query params has custom Log4om adif field: APP_L4ONG_QSO_AWARD_REFERENCES
    '''
    params = request.query_params

    endpoint = get_endpoint(params, LOG4OM_PORT, LOG4OM_HOST)

    adif_msg = build_adif(params)

    log_qso(adif_msg)

    try:
        send_msg(endpoint["host"], endpoint["port"], socket.SOCK_DGRAM, adif_msg)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"error in send_msg: {print(ex)}")

    return {"status": "true"}


@app.get("/log4om/ping")
async def log4om_ping(request: Request):
    # params = request.query_params
    # endpoint = get_endpoint(params, LOG4OM_PORT, LOG4OM_HOST)
    # ping(endpoint["host"], endpoint["port"], socket.SOCK_DGRAM)
    return {"status": "not impl"}


@app.get("/omnirig/qsy")
async def omnirig_qsy(request: Request):
    modes = {
        "USB": 0x02000000,
        "LSB": 0x04000000,
        "DATA-U": 0x08000000,
        "DATA-L": 0x10000000,
        "AM": 0x20000000,
        "FM": 0x40000000,
        "CW": 0x00800000,
        "CW-U": 0x00800000,
        "CW-L": 0x01000000
    }

    # from OmniRig.ridl
    RigParamX = {
        'PM_XITON': 0x0008_0000, 
        'PM_XITOFF': 0x0010_0000, 
        'PM_VFOA':  0x0000_0800,
        'PM_VFOB':  0x0000_1000,
        'PM_VFOAA': 0x0000_0080,
        'PM_VFOAB': 0x0000_0100,
        'PM_VFOBA': 0x0000_0200,
        'PM_VFOBB': 0x0000_0400,
    }

    freq = int(request.query_params["freq"])
    mode = request.query_params["mode"]
    rig_name = request.query_params.get("__port", "Rig1")
    # print(f"f {freq} m {mode} n {rig_name}")

    try:
        rig = getattr(omnirig, rig_name)
        print(rig.StatusStr)
        print(rig.RigType)
        rig.Mode = modes[mode]

        if (mode.startswith("CW")):
            if (config['cw_rit'] != 0):
                rig.Rit = config['cw_rit']  # this doesn't work on G-90
                freq += config['cw_rit']

        if config["g90"]:
            rig.Freq = freq
        else:
            #rig.SetSimplexMode(freq)
            # ok this method will clear out our Xit or Rit if used. try this
            # for other non-G90 rigs
            rig.FreqA = freq

        # XIT checks
        if not config["cw_xit"]:
            return
        
        time.sleep(0.25)

        xit = rig.Xit
        print(f"xit value is: {xit}")

        if mode.startswith("CW"):
            if xit != RigParamX["PM_XITON"]:
                print("turning XIT ON")
                rig.Xit = RigParamX["PM_XITON"]
        else:
            if xit == RigParamX["PM_XITON"]:
                print("turning XIT OFF")
                rig.Xit = RigParamX["PM_XITOFF"]

    except AttributeError as ae:
        print(f"Error Rig name is most likely invalid: {ae}")
        return {"status": "Error: Rig name is most likely invalid:"}

    return {"status": "success"}


@app.get("/aclog/ADDADIFRECORD")
async def aclog_log(request: Request):
    params = request.query_params

    endpoint = get_endpoint(params, ACLOG_PORT, ACLOG_HOST)
    qso = build_adif(params)
    adif_msg = f"<CMD><ADDADIFRECORD><VALUE>{qso}</VALUE></CMD>"

    try:
        send_msg(endpoint["host"], endpoint["port"], socket.SOCK_STREAM, adif_msg)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"error in send_msg: {print(ex)}")        

    return {"status": "true"}

'''
// dan
// number: is for sorting in ham-apps-proxy - aclog needs these to be in order
url = baseURL + "/aclog/?"
    + "01:<CMD><ACTION><VALUE>CLEAR</VALUE></CMD>"
    + "&02:<CMD><UPDATE><CONTROL>TXTENTRYCALL</CONTROL><VALUE>__CALL__</VALUE></CMD>"
    + "&03:<CMD><ACTION><VALUE>CALLTAB</VALUE></CMD>"
    + "&04:<CMD><UPDATE><CONTROL>TXTENTRYFREQUENCY</CONTROL><VALUE>" + (freq / 1000.0) + "</VALUE></CMD>"
    + "&05:<CMD><UPDATE><CONTROL>TXTENTRYMODE</CONTROL><VALUE>" + mode + "</VALUE></CMD>"
    + "&06:<CMD><UPDATE><CONTROL>TXTENTRYDATE</CONTROL><VALUE>" + new Date().toISOString().slice(0 ,10).replaceAll("-","/") + "</VALUE></CMD>"
    + "&07:<CMD><UPDATE><CONTROL>TXTENTRYTIMEON</CONTROL><VALUE>" + new Date().toISOString().slice(11,16) + "</VALUE></CMD>"
    + "&08:<CMD><UPDATE><CONTROL>TXTENTRYTIMEOFF</CONTROL><VALUE>" + new Date().toISOString().slice(11,16) + "</VALUE></CMD>"
    + "&09:<CMD><UPDATE><CONTROL>TXTENTRYRSTR</CONTROL><VALUE>__RST_RCVD__</VALUE></CMD>"
    + "&10:<CMD><UPDATE><CONTROL>TXTENTRYRSTS</CONTROL><VALUE>__RST_SENT__</VALUE></CMD>"
    + "&11:<CMD><UPDATE><CONTROL>TXTENTRYCOMMENTS</CONTROL><VALUE>" + commentStr + "</VALUE></CMD>"
    + "&12:<CMD><ACTION><VALUE>ENTER</VALUE></CMD>"
'''


@app.get("/aclog/changefreq")
async def aclog_changefreq(request: Request):
    params = request.query_params
    freq = float(params["value"])
    x = params["suppressmodedefault"]

    endpoint = get_endpoint(params, ACLOG_PORT, ACLOG_HOST)
    adif_msg = f"<CMD><CHANGEFREQ><VALUE>{freq}</VALUE><SUPPRESSMODEDEFAULT>{x}</SUPPRESSMODEDEFAULT</CMD>"
    send_msg(endpoint["host"], endpoint["port"], socket.SOCK_STREAM, adif_msg)

    return {"status": "true"}


@app.get("/aclog/changemode")
async def aclog_changemode(request: Request):
    params = request.query_params

    mode = params["value"]
    endpoint = get_endpoint(params, ACLOG_PORT, ACLOG_HOST)
    adif_msg = f"<CMD><CHANGEMODE><VALUE>{mode}</VALUE></CMD>"
    send_msg(endpoint["host"], endpoint["port"], socket.SOCK_STREAM, adif_msg)

    return {"status": "true"}


@app.on_event('shutdown')
def shutdown_event():
    print('potaplus_proxy shutdown handler')
    global omnirig
    omnirig = None

def ping(host: str, port: int, type: int):
    try:
        with socket.socket(socket.AF_INET, type) as sock:
            sock.bind((host, port))
            sock.listen(7)
    except Exception as ex:
        # i think the og intent its that its supposed to fail???
        print(ex)


def adif(field_name, input: str) -> str:
    size = len(input)
    return f"<{field_name}:{size}>{input}"


def build_adif(params):
    '''Builds an ADIF string based on the key value pairs given in 'params'
    
    The dictionary key names should probably be valid ADIF fields. This method 
    ignores potaplus added __host and __port query params.

    Parameters:
    params (dict): see request.query_params

    Returns (str): ADIF record
    '''
    adif_msg = ""

    for x in params:
        #print(x)
        if (x == "__port" or x == "__host"):
            continue  # skip. it's not adif
        adif_msg += adif(x, params[x])

    adif_msg += "<EOR>"
    return adif_msg


def get_endpoint(params, default_port: int, default_host: str) -> {}:
    ep = {}
    ep["port"] = int(params.get("__port", str(default_port)))
    ep["host"] = params.get("__host", default_host)

    return ep


def send_msg(host: str, port: int, type: int, msg: str):
    try:
        #print(f"sending adif to {host}:{port}")
        with socket.socket(socket.AF_INET, type) as sock:
            sock.connect((host, port))
            sock.send(msg.encode())
    except Exception as err:
        print("send_msg exception:", err)
        raise

def log_qso(adif: str):
    with open(BACKUP_LOG_FN, "a", encoding='UTF-8') as file:
        file.write(adif + "\n")

# when we run out of a bundled exe this is what starts off the application
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='ham-apps-proxy PYTHON',
        description='Provides endpoints for POTA PLUS website extension for https://pota.app',
        epilog='')

    parser.add_argument('-r', '--rit', default=0, type=int, help='If non-zero, apply an offset in HZ when QSYing to a CW spot.')
    parser.add_argument('-g', '--g90', action='store_true', help='If given, QSY differently for a Xiegu G90.')
    parser.add_argument('-x', '--xit', action='store_true', help='If given, turn on XIT for CW. Turn off XIT for other modes.')

    args = parser.parse_args()

    config['cw_rit'] = args.rit
    config["cw_xit"] = args.xit
    config['g90_qsy'] = args.g90

    if not os.path.exists(BACKUP_LOG_FN):
        with open(BACKUP_LOG_FN, "w", encoding='UTF-8') as f:
            f.write("HAM-APPS-PROXY PY backup log\n")
            f.write(f"Created {datetime.datetime.now()}\n")
            f.write(adif("programid", "ham-apps-proxy_py") + "\n")
            f.write(adif("programversion", VER) + "\n")
            f.write("<EOH>\n")

    uvicorn.run(app, host="0.0.0.0", port=8073)
