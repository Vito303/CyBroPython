# CyBroPython

### Install:
> apt install python <br>
> apt install python-pip <br>
> pip install pytz <br>
> pip install zerorpc <br>
> npm install

### Run node server:
> node server.js

### Test call 
#### Reading value:
> http://localhost:4000/get?tag=c17598.MyInt

#### Writing value:
> http://localhost:4000/set?tag=c17598.MyInt&value=42


# CyBroPython SCGI

### Run SCGI server:
~/Projects/CyBroPython/CyBroScgiServer/src$ python cybro_scgi_server.py

### Test call 
#### Reading value:
/Projects/CyBroPython/CyBroScgiServer/src$ python cybro_com_server.py "c110.Bulb0"


