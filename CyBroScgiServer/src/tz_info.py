import datetime
import const

try:
    import pytz
except ImportError:
    print "Fatal error: pytz library not found! Check http://sourceforge.net/projects/pytz/"
    quit()


#*****************************************************************************


class TimezoneInfoItem:

    nad = 0
    timezone_str = ""
    tzinfo = None

    #-------------------------------------------------------------------------

    def __init__(self, nad, timezone_str):
        self.nad = nad
        self.set_timezone_str(timezone_str)

    #-------------------------------------------------------------------------

    def set_timezone_str(self, s):
        self.timezone_str = s
        try:
            self.tzinfo = pytz.timezone(s)
        except:
            self.tzinfo = pytz.utc
            self.timezone_str = "UTC"

    #-------------------------------------------------------------------------


#*****************************************************************************


class TimezoneInfo:

    items = None

    #-------------------------------------------------------------------------

    def __init__(self):
        self.clear()

    #-------------------------------------------------------------------------

    def clear(self):
        self.items = []

    #-------------------------------------------------------------------------

    def add(self, nad, timezone_str):
        item = self.get(nad)
        if item != None:
            # update existing
            item.set_timezone_str(timezone_str)
        else:
            # create new
            self.items.append(TimezoneInfoItem(nad, timezone_str))

    #-------------------------------------------------------------------------

    def get(self, nad):
        for item in self.items:
            if item.nad == nad:
                return item
        return None

    #-------------------------------------------------------------------------

    def get_local_datetime(self, nad, dt = None):
        item = self.get(nad)
        if item != None:
            dt = dt if dt != None else self.get_utc_datetime()
            return dt.astimezone(item.tzinfo)
        else:
            return dt if dt != None else self.get_utc_datetime()

    #-------------------------------------------------------------------------

    def get_utc_datetime(self):
        return datetime.datetime.now(pytz.utc)

    #-------------------------------------------------------------------------

    def get_local_datetime_str(self, nad, dt = None, timezone = False):
        try:
            return self.get_local_datetime(nad, dt).strftime(const.TimeformatTz if timezone else const.Timeformat)
        except:
            return self.get_local_datetime(nad).strftime(const.TimeformatTz if timezone else const.Timeformat)

    #-------------------------------------------------------------------------

    def get_utc_datetime_str(self, nad, timezone = False):
        return self.get_local_datetime(nad).strftime(const.TimeformatTz if timezone else const.Timeformat)

    #-------------------------------------------------------------------------

    def get_timezone_str(self, nad):
        item = self.get(nad)
        return item.timezone_str if item != None else "UTC"

    #-------------------------------------------------------------------------


#*****************************************************************************
