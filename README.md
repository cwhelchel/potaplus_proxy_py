# ham-apps-proxy-py

A drop in replacement for the ham-apps-proxy used by POTA plus chrome browser 
extension

## Build notes

This little ditty needs Pyton 3, fast api, uvicorn. See ```requirements.txt```

First, setup a virtual environment and activate it:

    $ python -m venv ./virtenv/
    $ .\virtenv\Scripts\activate

Next install dependencies:    

    $ python -m pip install -r requirements.txt

Then your ready to build. To build the single exe use this command:

    $ pyinstaller ham-apps-proxy.spec