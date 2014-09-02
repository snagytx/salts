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
import xbmc
import urllib
import urlparse
import re
import common
from salts_lib.db_utils import DB_Connection
from salts_lib import log_utils
from salts_lib.constants import VIDEO_TYPES
from salts_lib.constants import QUALITIES


QUALITY_MAP = {'HD': QUALITIES.HIGH, 'LOW': QUALITIES.LOW}

class UFlix_Scraper(scraper.Scraper):
    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.base_url = 'http://twomovies.us'
        self.timeout=timeout
        self.db_connection = DB_Connection()
    
    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.SEASON, VIDEO_TYPES.EPISODE, VIDEO_TYPES.MOVIE])
    
    def get_name(self):
        return '2movies'
    
    def resolve_link(self, link):
        url = urlparse.urljoin(self.base_url, link)
        html = self.__http_get(url, cookie={'links_tos': '1'}, cache_limit=0)
        match = re.search('<iframe.*?src="([^"]+)', html, re.DOTALL)
        if match:
            return match.group(1)
    
    def format_source_label(self, item):
        return '[%s] %s (%s/100)' % (item['quality'], item['host'], item['rating'])
    
    def get_sources(self, video_type, title, year, season='', episode=''):
        sources=[]
        source_url=self.get_url(video_type, title, year, season, episode)
        if source_url:
            url = urlparse.urljoin(self.base_url, source_url)
            html = self.__http_get(url, cache_limit=.5)
    
            pattern='class="playDiv3".*?href="([^"]+).*?>(.*?)</a>'
            for match in re.finditer(pattern, html, re.DOTALL | re.I):
                url, host = match.groups()
                source = {'multi-part': False}
                source['url']=url.replace(self.base_url,'')
                source['host']=host
                source['class']=self
                source['quality']=None
                source['rating']=None
                source['views']=None
                sources.append(source)
            
        return sources

    def get_url(self, video_type, title, year, season='', episode=''):
        temp_video_type=video_type
        if video_type == VIDEO_TYPES.EPISODE: temp_video_type=VIDEO_TYPES.TVSHOW
        url = None

        result = self.db_connection.get_related_url(temp_video_type, title, year, self.get_name())
        if result:
            url=result[0][0]
            log_utils.log('Got local related url: |%s|%s|%s|%s|%s|' % (temp_video_type, title, year, self.get_name(), url))
        else:
            results = self.search(temp_video_type, title, year)
            if results:
                url = results[0]['url']
                self.db_connection.set_related_url(temp_video_type, title, year, self.get_name(), url)

        if url and video_type==VIDEO_TYPES.EPISODE:
            result = self.db_connection.get_related_url(VIDEO_TYPES.EPISODE, title, year, self.get_name(), season, episode)
            if result:
                url=result[0][0]
                log_utils.log('Got local related url: |%s|%s|%s|%s|%s|%s|%s|' % (video_type, title, year, season, episode, self.get_name(), url))
            else:
                show_url = url
                url = self.__get_episode_url(show_url, season, episode)
                if url:
                    self.db_connection.set_related_url(VIDEO_TYPES.EPISODE, title, year, self.get_name(), url, season, episode)
        
        return url
    
    def search(self, video_type, title, year):
        search_url = urlparse.urljoin(self.base_url, '/search/?criteria=title&search_query=')
        search_url += urllib.quote_plus(title)
        html = self.__http_get(search_url, cache_limit=.25)
        results=[]
        
        # filter the html down to only tvshow or movie results
        if video_type in [VIDEO_TYPES.TVSHOW, VIDEO_TYPES.SEASON, VIDEO_TYPES.EPISODE]:
            pattern='<h1>Tv Shows</h1>.*'
        else:
            pattern='<div class="filmDiv".*(<h1>Tv Shows</h1>)*'
        match = re.search(pattern, html, re.DOTALL)
        try:
            fragment = match.group(0)
            pattern = 'href="([^"]+)" class="filmname">(.*?)\s*</a>.*?/all/byViews/(\d+)/'
            for match in re.finditer(pattern, fragment, re.DOTALL):
                result={}
                url, res_title, res_year = match.groups('')
                if not year or year == res_year:                
                    result['title']=res_title
                    result['url']=url.replace(self.base_url,'')
                    result['year']=res_year
                    results.append(result)
        except Exception as e:
            log_utils.log('Failure during %s search: |%s|%s|%s| (%s)' % (self.get_name(), video_type, title, year, str(e)), xbmc.LOGWARNING)
        
        return results
        
    def __get_episode_url(self, show_url, season, episode):
        url = urlparse.urljoin(self.base_url, show_url)
        html = self.__http_get(url, cache_limit=2)
        pattern = 'class="linkname\d*" href="([^"]+/watch_episode/[^/]+/%s/%s/)"' % (season, episode)
        match = re.search(pattern, html)
        if match:
            url = match.group(1)
            return url.replace(self.base_url, '')
        
    def __http_get(self, url, cookie=None, cache_limit=8):
        return common.cached_http_get(url, self.base_url, self.timeout, cookie, cache_limit=cache_limit)