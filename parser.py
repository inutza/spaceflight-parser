import urllib2
import re
from HTMLParser import HTMLParser
from datetime import datetime, date, time, timedelta
import pytz
from icalendar import Calendar, Event, vDatetime

# Tags which help extract each section
DATETAG = '<div class="datename"><span class="launchdate">'
SPANENDTAG = '</span>'
SPANSTARTTAG = '<span class="strong">'
DIVENDTAG = '</div>'
MISSIONTAG = '<span class="mission">'
LAUNCHWINDOWTAG = '<div class="missiondata"><span class="strong">Launch window:</span> '
GMT = ' GMT'
LOCTAG = 'Launch site:</span> '
DESCTAG = '<div class="missdescrip">'
UPDATETAG = '. ['
LAUNCHREGEX = '[0-9]+(-?[0-9]+)'

# Short-hand months and full name months -- hope they don't change
SH_MTH = ['Jan.', 'Feb.', 'Mar.', 'Apr.', 'May', 'Jun.', 'Jul.', 'Aug.', 'Sept.', 'Oct.', 'Nov.', 'Dec.']
FL_MTH = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']


def parser():
    
    req = urllib2.Request('https://spaceflightnow.com/launch-schedule/')
    response = urllib2.urlopen(req)
    the_page = response.read()
   
    d = datetime.utcnow()
    h = HTMLParser()
    cal = Calendar()
    cal.add('version', 2.0)
    cal.add('prodid', '-//madkat//SpaceX feed//EN')
    
    # Get all DATETAG indexes
    date_group = [m.start() for m in re.finditer(DATETAG, the_page)]
    
    # For each date index in date_group, extract the other data
    for _idx in range(len(date_group)):

        date_idx = date_group[_idx]
        if _idx + 1 == len(date_group):
            block_end = len(the_page)
        else:
            block_end = date_group[_idx + 1]
            
        date_start_idx = date_idx + len(DATETAG)
        date_end_idx = the_page[date_start_idx:block_end].find(SPANENDTAG) + date_start_idx
        date = the_page[date_start_idx:date_end_idx]

        found_month = False
        mth_idx = 0
        
        while not found_month and mth_idx < 12:
            if SH_MTH[mth_idx] in date:
                _idx = date.find(SH_MTH[mth_idx])
                day = date[_idx + len(SH_MTH[mth_idx]) + 1:]
                found_month = True
                break
            if FL_MTH[mth_idx] in date:
                _idx = date.find(FL_MTH[mth_idx])
                day = date[_idx + len(FL_MTH[mth_idx]) + 1:]
                found_month = True
                break
            mth_idx += 1

        # If I find a day, or month, start building datetime object
        # Otherwise, I just skip the event
        if found_month and day != '':
            event = Event()
            # Check if day has '/' in it
            if '/' in day:
                _idx = day.find('/')
                day = day[_idx+1:]
            ev_date = datetime(d.year, d.month, d.day, d.hour, d.minute, 0, 0, tzinfo=pytz.utc)
            mth = mth_idx + 1
            if mth < d.month:
                # It's next year (pray it holds -- worst case scenario it fixes itself in Jan?)
                ev_date = ev_date.replace(year = ev_date.year + 1)
            ev_date = ev_date.replace(month = mth)
            ev_date = ev_date.replace(day = int(day))
        
            # Get event title
            mission_start_idx = the_page[date_end_idx:block_end].find(MISSIONTAG) + len(MISSIONTAG) + date_end_idx
            mission_end_idx = the_page[mission_start_idx:block_end].find(SPANENDTAG) + mission_start_idx
            mission = the_page[mission_start_idx:mission_end_idx]
            mission = re.sub(r'[^\x00-\x7F]+','-', mission)
            # Escape all sorts of weird characters
            mission = mission.decode("ascii", errors="ignore").encode()
            # Escape HTML characters & add summary
            event.add('summary', h.unescape(mission))
        
            # Get launch window
            launch_win_start_idx = the_page[mission_end_idx:block_end].find(LAUNCHWINDOWTAG) + len(LAUNCHWINDOWTAG) + mission_end_idx
            launch_win_end_idx = the_page[launch_win_start_idx:block_end].find(SPANSTARTTAG) + launch_win_start_idx
            launch_win_raw = the_page[launch_win_start_idx:launch_win_end_idx]
            is_gmt_idx = launch_win_raw.find(GMT)
            # If there is no launch window yet, just make it a 24hr event (all day equivalent?)
            if is_gmt_idx == -1:
                launch_win = "0000-2359"
            else:
                launch_win = re.search(LAUNCHREGEX, launch_win_raw[:is_gmt_idx]).group(0)
            
            # Parse launch window
            if '-' in launch_win:
                # I have a launch window!
                ev_date = ev_date.replace(hour = int(launch_win[:2]))
                ev_date = ev_date.replace(minute = int(launch_win[2:4]))
                ev_date_end = ev_date.replace(hour = int(launch_win[5:7]))
                ev_date_end = ev_date_end.replace(minute = int(launch_win[7:]))
            else:
                ev_date = ev_date.replace(hour = int(launch_win[:2]))
                ev_date = ev_date.replace(minute = int(launch_win[2:]))
                ev_date_end = ev_date + timedelta(hours=1)

            event.add('dtstart', ev_date)
            event.add('dtend', ev_date_end)
            
            # Get event location
            loc_start_idx = the_page[launch_win_end_idx:block_end].find(LOCTAG) + len(LOCTAG) + launch_win_end_idx
            loc_end_idx = the_page[loc_start_idx:block_end].find(DIVENDTAG) + loc_start_idx
            location = the_page[loc_start_idx:loc_end_idx]
            event.add('location', location)
            
            # Get event description
            desc_start_idx = the_page[launch_win_end_idx:block_end].find(DESCTAG)  + launch_win_end_idx + len(DESCTAG)
            desc_end_idx = the_page[desc_start_idx:block_end].find(UPDATETAG) + desc_start_idx
            desc = the_page[desc_start_idx:desc_end_idx].decode("ascii", errors="ignore").encode()
            desc_filtered = h.unescape(desc)
            # If it didn't have a launch window, write a comment in description
            if launch_win == "0000-2359":
                desc_filtered = "Launch window currently unavailable. Please check at a later time. " + desc_filtered
            event.add('description', desc_filtered)
            
            # Add event to calendar
            cal.add_component(event)
        
    # Return calendar
    return cal.to_ical()
    

if __name__ == '__main__':
    print parser()