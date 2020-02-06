# CyBroPython

### Install Linux:
> apt install python <br>
> apt install python-pip <br>

### Install Windows:
> install python 2.7 (https://www.python.org/downloads/windows/) <br>
> curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py <br>
> python get-pip.py <br>

### Install Python libs:
> pip install pytz <br>
> pip install zerorpc <br>

### Install Nodejs:
> npm install

### Run Node server:
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


