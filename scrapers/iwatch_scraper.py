"""
    SALTS XBMC Addon
    Copyright (C) 2014 tknorris

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import scraper
import re
import urllib
import urlparse
import time
import xbmcaddon
import xbmc
from salts_lib.db_utils import DB_Connection
from salts_lib import log_utils
from salts_lib.constants import VIDEO_TYPES
from salts_lib.constants import QUALITIES

QUALITY_MAP = {'HD': QUALITIES.HD, 'HDTV': QUALITIES.HIGH, 'DVD': QUALITIES.HIGH, '3D': QUALITIES.HIGH, 'CAM': QUALITIES.LOW}
BASE_URL = 'http://www.iwatchonline.to'

class IWatchOnline_Scraper(scraper.Scraper):
    base_url=BASE_URL
    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout=timeout
        self.db_connection = DB_Connection()
        self.base_url = xbmcaddon.Addon().getSetting('%s-base_url' % (self.get_name()))
   
    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.SEASON, VIDEO_TYPES.EPISODE, VIDEO_TYPES.MOVIE])
    
    @classmethod
    def get_name(cls):
        return 'IWatchOnline'
    
    def resolve_link(self, link):
        url = urlparse.urljoin(self.base_url, link)
        html = self._http_get(url, cache_limit=.5)
        match = re.search('<iframe name="frame" class="frame" src="([^"]+)', html)
        if match:
            return match.group(1)
    
    def format_source_label(self, item):
        label='[%s] %s (%s/100) ' % (item['quality'], item['host'], item['rating'])
        return label
    
    def get_sources(self, video):
        source_url=self.get_url(video)
        hosters = []
        if source_url:
            url = urlparse.urljoin(self.base_url, source_url)
            html = self._http_get(url, cache_limit=.5)
            
            match = re.search('<table[^>]+id="streamlinks">(.*?)</table>', html, re.DOTALL)
            if match:
                fragment = match.group(1)
                pattern = 'href="([^"]+/play/[^"]+).*?/>\s+\.?([^<]+?)\s+.*?class="linkdate">(\d+).*?<td>([^<]+)'
                max = 0
                min = int(time.time())
                for match in re.finditer(pattern, fragment, re.DOTALL):
                    url, host, age, quality = match.groups()
                    age = int(age)
                    if age>max: max=age
                    if age<min: min=age
                    hoster = {'multi-part': False, 'class': self, 'url': url.replace(self.base_url,''), 'host': host, 'age': age, 'views': None, 'rating': None}
                    hoster['quality']=QUALITY_MAP[quality] if quality in QUALITY_MAP else None
                    hosters.append(hoster)
                
                unit=(max-min)/100
                print '%s, %s, %s' % (min, max, unit)
                for hoster in hosters:
                    hoster['rating']=(100-(hoster['age']-min)/unit)
        return hosters

    def get_url(self, video):
        return super(IWatchOnline_Scraper, self)._default_get_url(video)
    
    def search(self, video_type, title, year):
        search_url = urlparse.urljoin(self.base_url, '/advance-search')
        if video_type == VIDEO_TYPES.MOVIE:
            data = {'searchin': '1'}
        else:
            data = {'searchin': '2'}
        data.update({'searchquery': title})
        search_url += '?' + urllib.urlencode(data) # add criteria to url to make cache work        
        html = self._http_get(search_url, data=data, cache_limit=.25)

        results=[]
        pattern = r'href="([^"]+)">(.*?)\s+\((\d{4})\)'
        for match in re.finditer(pattern, html):
            url, title, year = match.groups('')
            url = url.replace('/episode/', '/tv-shows/') # fix wrong url returned from search results
            result={'url': url.replace(self.base_url,''), 'title': title, 'year': year}
            results.append(result)
        return results
    
    def _get_episode_url(self, show_url, season, episode, ep_title):
        episode_pattern = 'href="([^"]+-s%02de%02d)"' % (int(season), int(episode))
        title_pattern='href="([^"]+)"><i class="icon-play-circle">.*?<td>([^<]+)</td>'
        return super(IWatchOnline_Scraper, self)._default_get_episode_url(show_url, season, episode, ep_title, episode_pattern, title_pattern)
        
    def _http_get(self, url, data=None, cache_limit=8):
        return super(IWatchOnline_Scraper, self)._cached_http_get(url, self.base_url, self.timeout, data=data, cache_limit=cache_limit)
