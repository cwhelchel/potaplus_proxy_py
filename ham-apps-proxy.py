# http://localhost:8000/log4om/log?CALL=KQ4DAP&RST_SENT=599&RST_RCVD=599&FREQ=14.045&FREQ_RX=14.045&MODE=CW&COMMENT=[POTA%20K-3377%20US-NE%20EN21ba%20Schilling%20Wildlife%20Management%20Area]%20&QSO_DATE=20230801&TIME_ON=171143&TX_PWR=&RX_PWR=&APP_L4ONG_QSO_AWARD_REFERENCES=[{%22AC%22:%22POTA%22,%22R%22:%22K-3377%22,%22G%22:%22US-NE%22,%22SUB%22:[],%22GRA%22:[]}]&__port=

import argparse
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
omnirig = win32com.client.Dispatch("{0839E8C6-ED30-4950-8087-966F970F0CAE}")
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

VER = "0.0.0a"
LOG4OM_HOST = "localhost"
LOG4OM_PORT = 2239
ACLOG_HOST = "localhost"
ACLOG_PORT = 1100

config = {
    'cw_rit': 10 # offset in HZ, if nonzero is added to freq 
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

    freq = int(request.query_params["freq"])
    mode = request.query_params["mode"]
    rig_name = request.query_params.get("__port", "Rig1")
    # print(f"f {freq} m {mode} n {rig_name}")

    try:
        rig = getattr(omnirig, rig_name)
        print(rig.StatusStr)
        print(rig.RigType)
        rig.Mode = modes[mode]

        # this doesn't work on G-90
        if (mode.startswith("CW")):
            rig.Rit = 10
            if (config['cw_rit'] != 0):
                freq += config['cw_rit']

        rig.Freq = freq
    except AttributeError as ae:
        print(f"Error Rig name is most likely invalid: {ae}")
        return {"status": "Error: Rig name is most likely invalid:"}

    return {"status": "success"}


@app.get("/aclog/ADDADIFRECORD")
async def aclog_log(request: Request):
    params = request.query_params

    endpoint = get_endpoint(params, ACLOG_PORT, ACLOG_HOST)
    adif_msg = f"<CMD><ADDADIFRECORD><VALUE>{build_adif(params)}</VALUE></CMD>"

    try:
        send_msg(endpoint["host"], endpoint["port"], socket.SOCK_STREAM, adif_msg)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"error in send_msg: {print(ex)}")        

    return {"status": "true"}


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


# when we run out of a bundled exe this is what starts off the application
if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='ham-apps-proxy PYTHON',
        description='Provides endpoints for POTA PLUS website extension for https://pota.app',
        epilog='')
    
    parser.add_argument('-r', '--rit', default=0, type=int, help='If non-zero, apply an offset in HZ when QSYing to a CW spot.')

    args = parser.parse_args()

    config['cw_rit'] = args.rit

    uvicorn.run(app, host="0.0.0.0", port=8073)
