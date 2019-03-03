import globals, os

# application directories
AppDir = os.path.realpath(os.path.dirname(__file__)) + "/"
AllocationDirectory = os.path.normpath(AppDir + "../alc/")
LogDirectory = os.path.normpath(AppDir + "../log/")
ConfigIniFilename = "scgi_server.ini"
ConfigIni = os.path.normpath(AppDir + "../" + ConfigIniFilename)
DataLoggerConfig = os.path.normpath(AppDir + "../data_logger.xml")

# push server settings
PushEnable = True # enable/disable push server
ReadAllocAfterPush = True # check allocation file each time push is received
InterfaceBindAddress = "" # empty for LAN operation, static WAN IP for internet operation
PushTimeout = 24 # time after which cybro is removed from the push list [hours]
LocalAccess = True # true for LAN operation, false for internet operation
BroadcastAddress = "255.255.255.255" # broadcast address used for LAN IP autodetect
PushPort = 8442 # udp listener for push messages and A-bus communication port
AlcTimeout = 60 # interval for checking project timeout [sec]
CacheRequest = 2 # [sec], time after which data is still read from cache, but new read message is generated, 0 for no requests until cache expires
CacheValid = 5 # [sec], time after which cached value is invalidated, -1 to disable cache

# default controller settings
ConnectionType = "LAN" # LAN | WAN | GSM, communication timeout and retry count
Password = "" # A-bus password, set by CyPro/Configuration/Protection, default is empty
TransactionId = True # message transaction id, not used if password is not empty

# timeout and retry values for ConnectionType=LAN | WAN | GSM
LanTimeout = 200 # [msec]
LanRetry = 3
WanTimeout = 2000 # [msec]
WanRetry = 3
GsmTimeout = 5000 # [msec]
GsmRetry = 3

# scgi server settings
UseHTTPProtocol = False
ScgiServerURL = "http://localhost/scgi/" # for Webfaction use "http://www.solar-cybro.com/scgi/"
ScgiServerPort = 4000 # for webfaction use port given for "scgi_server" application
CacheCleanupPeriod = 120 # sec
ScgiRequestTimeout = 10 # sec
ConfigIniCheckPeriod = 10 # sec
MaxFrameDataBytes = 1000 # max A-bus frame size

# database settings
DatabaseEngine = "mysql"
DatabaseHost = "localhost"
DatabaseName = "solar"
DatabaseUser = "root"
DatabasePassword = "solar"
DatabaseDataLoggerSamplesTable = "measurements"
DatabaseDataLoggerAlarmsTable = "alarms"
DatabaseDataRelayDataTable = "relays"
DatabaseDataControllersTable = "controllers"

# data logger settings
DataLoggerEnable = False

# data digger settings
DataDiggerEnable = False

# relay settings
RelayEnable = False

# debug log
LogEnable = False
DebugComm = False
DebugPrints = False
DebugRConsole = False
DebugTcpServer = False
DebugTcpServerPort = 4001 # for Webfaction use port given for "debug_port" application
MaxLogFilesize = 1024 # kB
LogBackupCount = 2 # number of backup copies
