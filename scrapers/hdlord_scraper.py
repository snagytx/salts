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
import urlparse
import xbmcaddon
import xbmc
import base64
import urllib
import json
from salts_lib.db_utils import DB_Connection
from salts_lib import GKDecrypter
from salts_lib import log_utils
from salts_lib.constants import VIDEO_TYPES
from salts_lib.constants import QUALITIES
from salts_lib.constants import USER_AGENT

BASE_URL = 'http://hdlord.com'
QUALITY_MAP = {'mobile': QUALITIES.LOW, 'lowest': QUALITIES.LOW, 'low': QUALITIES.MEDIUM, 'sd': QUALITIES.HIGH, 'hd': QUALITIES.HD}
OD_META_URL = 'http://www.odnoklassniki.ru/dk?cmd=videoPlayerMetadata&mid=%s'

class HDLord_Scraper(scraper.Scraper):
    base_url=BASE_URL
    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout=timeout
        self.db_connection = DB_Connection()
        self.base_url = xbmcaddon.Addon().getSetting('%s-base_url' % (self.get_name()))
   
    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE])
    
    @classmethod
    def get_name(cls):
        return 'HDLord'
    
    def resolve_link(self, link):
        return link
    
    def format_source_label(self, item):
        label='[%s]' % (item['quality'])
        if 'res' in item: label = '%s (%s)' % (label, item['res'])
        label = '%s %s (%s views)' % (label, item['host'], item['views'])
        return label
    
    def get_sources(self, video):
        source_url=self.get_url(video)
        hosters = []
        if source_url:
            url = urlparse.urljoin(self.base_url, source_url)
            html = self._http_get(url, cache_limit=.5)
            
            views = None
            match = re.search('>Total Views<.*?<span>(\d+)', html)
            if match:
                views = match.group(1)
                
            seen_urls = []
            for match in re.finditer('proxy\.link\s*=\s*([^&"]+)', html):
                proxy_link = match.group(1)
                proxy_link = proxy_link.split('*', 1)[-1]
                proxy_link = proxy_link.strip()
                stream_url = GKDecrypter.decrypter(198,128).decrypt(proxy_link, base64.urlsafe_b64decode('dWhhVnA4R3Z5a2N5MWJGUWFmQlI='),'ECB').split('\0')[0]
                host = urlparse.urlsplit(stream_url).hostname
                
                if host and stream_url not in seen_urls:
                    if 'odnoklassniki.ru' in stream_url:
                        sources = self.parse_format(stream_url)
                        host = 'hdlord.com'
                        direct = True
                    elif 'google.com' in stream_url:
                        sources = self.parse_format2(stream_url)
                        host = 'hdlord.com'
                        direct = True
                    else:
                        sources = [{'url': stream_url, 'quality': QUALITIES.HD}]
                        direct = False
                        
                    for source in sources:
                        hoster = {'multi-part': False, 'class': self, 'host': host, 'rating': None, 'views': views, 'direct': direct}
                        hoster.update(source)
                        hosters.append(hoster)
                seen_urls.append(stream_url)
         
        return hosters

    def parse_format(self, host_url):
        video_id = host_url.rsplit('/',1)[-1]
        host_url =  OD_META_URL % (video_id)
        html = self._http_get(host_url, cache_limit=.5)
        js_result = json.loads(html)
        sources = []
        if 'videos' in js_result:
            for video in js_result['videos']:
                url = video['url'] + '&start=0|User-Agent=%s' % (USER_AGENT)
                source = {'url': url, 'quality': QUALITY_MAP.get(video['name'], QUALITIES.MEDIUM)}
                sources.append(source)
        return sources
    
    def parse_format2(self, host_url):
        html = self._http_get(host_url, cache_limit=.5)
        html = re.sub('\s','', html)
        match = re.search(r'(\[\s*\[\d+,\d+,\d+.*?\]\s*\])', html)
        sources = []
        if match:
            html = match.group(1)
            html = html.replace('\\"', '"')
            html = html.replace('\\u0026', '&')
            html = html.replace('\\u003d', '=')
            html = html.replace('\\u003c', '<')
            html = html.replace('\\u003e', '>')
            for match in re.finditer('(\d+),\d+,"(https://redirector[^"]+)', html):
                width, url = match.groups()
                source = {'url': url}
                source.update(self.__set_quality(width))
                sources.append(source)
        return sources
     
    def __set_quality(self, width):
        width=int(width)
        if width>=1920:
            quality=QUALITIES.HD
            res='1080p'
        elif width>=1280:
            quality=QUALITIES.HD
            res = '720p'
        elif width>640:
            quality=QUALITIES.HIGH
            res='480p'
        else:
            quality=QUALITIES.MEDIUM
            res='360p'
        return {'quality': quality, 'res': res}
    
    def get_url(self, video):
        return super(HDLord_Scraper, self)._default_get_url(video)
    
    def search(self, video_type, title, year):
        search_url = urlparse.urljoin(self.base_url, '/browse_items.php')
        search_url += '?' + urllib.urlencode({'title': title, 'year': year})
        data = {'keyword': '%s %s' % (title, year)}
        html = self._http_get(search_url, data=data, cache_limit=.25)
        
        results=[]
        pattern = "href='([^']+)'\s+class='item_result_title'>\s*([^<]+)\s+\((\d{4})\)"
        for match in re.finditer(pattern, html, re.DOTALL):
            url, match_title, match_year = match.groups('')
            result = {'url': url.replace(self.base_url,''), 'title': match_title, 'year': match_year}
            results.append(result)
        return results
    
    def _http_get(self, url, data=None, cache_limit=8):
        return super(HDLord_Scraper, self)._cached_http_get(url, self.base_url, self.timeout, data=data, cache_limit=cache_limit)
