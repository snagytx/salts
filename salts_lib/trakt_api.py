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
import json
import urllib2
from urllib2 import HTTPError
import urllib
import hashlib
import re
import socket
import ssl
import time
import xbmc
import log_utils
from db_utils import DB_Connection
from constants import TRAKT_SECTIONS
from constants import TEMP_ERRORS
from constants import SECTIONS
from constants import TRAKT_SORT

class TraktError(Exception):
    pass

class TransientTraktError(Exception):
    pass

BASE_URL = 'api.v2.trakt.tv'
V2_API_KEY ='eb41e95243d8c95152ed72a1fc0394c93cb785cb33aed609fdde1a07454584b4'
RESULTS_LIMIT=10
    
class Trakt_API():
    def __init__(self, username, password, token=None, use_https=False, timeout=5):
        self.username = username
        self.password = password
        self.token = token
        self.protocol='https://' if use_https else 'http://'
        self.timeout=timeout
        
    def login(self):
        url = '/auth/login'
        data = {'login': self.username, 'password': self.password}
        response = self.__call_trakt(url, data, cached=False)
        return response['token']
    
    def show_list(self, slug, section, username=None, cached=True):
        if not username: 
            username = self.username
            cache_limit=0 # don't cache user's own lists at all
            cached=False
        else:
            cache_limit=1 # cache other user's list for one hour
 
        url='/users/%s/lists/%s/items' % (username, slug)
        params = {'extended': 'full,images'}
        list_data = self.__call_trakt(url, params=params, cache_limit=cache_limit, cached=cached)
        items=[]
        for item in list_data:
            if item['type']==TRAKT_SECTIONS[section][:-1]:
                show=item[item['type']]
                items.append(show)
        return items
     
    def show_watchlist(self, section):
        url='/users/%s/watchlist/%s' % (self.username, TRAKT_SECTIONS[section])
        params = {'extended': 'full,images'}
        response = self.__call_trakt(url, params=params, cache_limit=0)
        return [item[TRAKT_SECTIONS[section][:-1]] for item in response]
     
    def get_lists(self, username=None):
        if not username: username = self.username
        url='/users/%s/lists' % (username)
        return self.__call_trakt(url, cache_limit=0)
     
    def add_to_list(self, section, slug, items):
        return self.__manage_list('add', section, slug, items)
         
    def add_to_collection(self, section, item):
        return self.__manage_collection('add', section, item)
         
    def remove_from_collection(self, section, item):
        return self.__manage_collection('remove', section, item)
         
    def set_watched(self, section, item, season='', episode='', watched=True):
        url = '/sync/history'
        if not watched: url = url + '/remove'
        data = self.__make_media_list(section, item, season, episode)
        return self.__call_trakt(url, data=data, cache_limit=0)
     
    def remove_from_list(self, section, slug, items):
        return self.__manage_list('delete', section, slug, items)
     
    def add_to_watchlist(self, section, items):
        return self.__manage_watchlist('add', section, items)
         
    def remove_from_watchlist(self, section, items):
        return self.__manage_watchlist('remove', section, items)
    
    def get_trending(self, section):
        url='/%s/trending' % (TRAKT_SECTIONS[section])
        params = {'extended': 'full,images', 'limit': RESULTS_LIMIT}
        response=self.__call_trakt(url, params=params)
        return [item[TRAKT_SECTIONS[section][:-1]] for item in response]
    
    def get_popular(self, section):
        url='/%s/popular' % (TRAKT_SECTIONS[section])
        params = {'extended': 'full,images', 'limit': RESULTS_LIMIT}
        return self.__call_trakt(url, params=params)
    
    def get_genres(self, section):
        url='/genres/%s' % (TRAKT_SECTIONS[section])
        return self.__call_trakt(url, cache_limit=24)
        
    def get_recommendations(self, section):
        url='/recommendations/%s' % (TRAKT_SECTIONS[section])
        params = {'extended': 'full,images', 'limit': RESULTS_LIMIT}
        return self.__call_trakt(url, params=params)
         
#     def get_friends_activity(self, section, include_episodes=False):
#         if section == SECTIONS.TV:
#             types='show'
#             if include_episodes:
#                 types += ',episode'
#         elif section == SECTIONS.MOVIES:
#             types='movie'
# 
#         url='/activity/friends.json/%s/%s' % (API_KEY, types)
#         return self.__call_trakt(url)
#         
#     def get_calendar(self, start_date=None, cached=True):
#         url='/calendar/shows.json/%s' % (API_KEY)
#         if start_date: url += '/%s' % (start_date)
#         return self.__call_trakt(url, cached=cached)
#     
#     def get_premieres(self, start_date=None, cached=True):
#         url='/calendar/premieres.json/%s' % (API_KEY)
#         if start_date: url += '/%s' % (start_date)
#         return self.__call_trakt(url, cached=cached)
#     
#     def get_my_calendar(self, start_date=None, cached=True):
#         url='/user/calendar/shows.json/%s/%s' % (API_KEY, self.username)
#         if start_date: url += '/%s' % (start_date)
#         return self.__call_trakt(url, cached=cached)
#         
    def get_seasons(self, slug):
        url = '/shows/%s/seasons' % (slug)
        params = {'extended': 'full,images'}
        return self.__call_trakt(url, params=params, cache_limit=8)
     
    def get_episodes(self, slug, season):
        url = '/shows/%s/seasons/%s' % (slug, season)
        params = {'extended': 'full,images'}
        return self.__call_trakt(url, params=params, cache_limit=1)
     
    def get_show_details(self, slug):
        url = '/shows/%s' % (slug)
        params = {'extended': 'full,images'}
        return self.__call_trakt(url, params=params, cache_limit=8)
     
#     def get_episode_details(self, slug, season, episode):
#         url = '/show/episode/summary.json/%s/%s/%s/%s' % (API_KEY, slug, season, episode)
#         return self.__call_trakt(url, cache_limit=8)
#     
#     def get_movie_details(self, slug):
#         url = '/movie/summary.json/%s/%s' % (API_KEY, slug)
#         return self.__call_trakt(url, cache_limit=8)
#     
    def search(self, section, query):
        url='/search'
        params = {'type': TRAKT_SECTIONS[section][:-1], 'query': query}
        #params.update({'extended': 'full,images'})
        response = self.__call_trakt(url, params = params)
        return [item[TRAKT_SECTIONS[section][:-1]] for item in response]
         
    def get_collection(self, section, cached=True):
        url='/users/%s/collection/%s' % (self.username, TRAKT_SECTIONS[section])
        params = {'extended': 'full,images'}
        response = self.__call_trakt(url, params=params, cached=cached)
        return [item[TRAKT_SECTIONS[section][:-1]] for item in response]
     
#     def get_watched(self, section, cached=True):
#         url='/user/library/%s/watched.json/%s/%s/min' % (TRAKT_SECTIONS[section], API_KEY, self.username)
#         return self.__call_trakt(url, cached=cached)
#         
    def get_show_progress(self, slug, cached=True):
        url='/shows/%s/progress/watched' % (slug)
        return self.__call_trakt(url, cached=cached)
      
    def rate(self, section, item, rating, season='', episode=''):
        url ='/sync/ratings'
        data = self.__make_media_list(section, item, season, episode)
        
        if rating is None:
            url = url + '/remove'
        else:
            data[TRAKT_SECTIONS[section]][0].update({'rating': int(rating)})
            
        self.__call_trakt(url, data=data, cache_limit=0)
    
    def __get_user_attributes(self, item):
        show={}
        if 'watched' in item: show['watched']=item['watched']
        if 'in_collection' in item: show['in_collection']=item['in_collection']
        if 'in_watchlist' in item: show['in_watchlist']=item['in_watchlist']
        if 'rating' in item: show['rating']=item['rating']
        if 'rating_advanced' in item: show['rating_advanced']=item['rating_advanced']
        return show
    
    def __manage_list(self, action, section, slug, items):
        url='/users/%s/lists/%s/items' % (self.username, slug)
        if action == 'remove': url = url + '/remove'
        if not isinstance(items, (list,tuple)): items=[items]
        data = self.__make_media_list_from_list(section, items)
        return self.__call_trakt(url, data = data, cache_limit=0)
     
    def __manage_watchlist(self, action, section, items):
        url='/sync/watchlist'
        if action == 'remove': url = url + '/remove'
        if not isinstance(items, (list,tuple)): items=[items]
        data = self.__make_media_list_from_list(section, items)
        return self.__call_trakt(url, data = data, cache_limit=0)
     
    def __manage_collection(self, action, section, item):
        url = '/sync/collection'
        if action == 'remove': url = url + '/remove'
        data = self.__make_media_list(section, item)
        return self.__call_trakt(url, data = data, cache_limit=0)
        
    def __make_media_list(self, section, item, season = '', episode = ''):
        ids = {'ids': item}
        if section == SECTIONS.MOVIES:
            data = {'movies': [ids]}
        else:
            data = {'shows': [ids]}
            if season:
                data['shows'][0]['seasons']=[{'number': int(season)}]
                print data
                if episode:
                    data['shows'][0]['seasons'][0]['episodes']=[{'number':int(episode)}]
        return data
    
    def __make_media_list_from_list(self, section, items):
        data = {TRAKT_SECTIONS[section]: []}
        for item in items:
            ids = {'ids': item}
            data[TRAKT_SECTIONS[section]].append(ids)
        return data
    
    def __call_trakt(self, url, data = None, params=None, cache_limit=.25, cached=True):
        if not cached: cache_limit = 0
        json_data=json.dumps(data) if data else None
        headers = {'Content-Type': 'application/json', 'trakt-api-key': V2_API_KEY, 'trakt-api-version': 2, 'trakt-user-login': self.username, 'trakt-user-token': self.token}
        url = '%s%s%s' % (self.protocol, BASE_URL, url)
        if params: url = url + '?' + urllib.urlencode(params)
        log_utils.log('Trakt Call: %s, header: %s, data: %s' % (url, headers, data), xbmc.LOGDEBUG)

        db_connection = DB_Connection()
        created, cached_result = db_connection.get_cached_url(url)
        if cached_result and (time.time() - created) < (60 * 60 * cache_limit):
            result = cached_result
            log_utils.log('Returning cached result for: %s' % (url), xbmc.LOGDEBUG)
        else: 
            try:
                
                request = urllib2.Request(url, data = json_data, headers = headers )
                f=urllib2.urlopen(request, timeout = self.timeout)
                result=f.read()
                db_connection.cache_url(url, result)
            except (ssl.SSLError,socket.timeout)  as e:
                if cached_result:
                    result = cached_result
                    log_utils.log('Temporary Trakt Error (%s). Using Cached Page Instead.' % (str(e)), xbmc.LOGWARNING)
                else:
                    raise TransientTraktError('Temporary Trakt Error: '+str(e))
            except urllib2.URLError as e:
                if isinstance(e, urllib2.HTTPError):
                    if e.code in TEMP_ERRORS:
                        if cached_result:
                            result = cached_result
                            log_utils.log('Temporary Trakt Error (%s). Using Cached Page Instead.' % (str(e)), xbmc.LOGWARNING)
                        else:
                            raise TransientTraktError('Temporary Trakt Error: '+str(e))
                    elif e.code == 404:
                        return
                    else:
                        raise
                elif isinstance(e.reason, socket.timeout) or isinstance(e.reason, ssl.SSLError):
                    if cached_result:
                        result = cached_result
                        log_utils.log('Temporary Trakt Error (%s). Using Cached Page Instead' % (str(e)), xbmc.LOGWARNING)
                    else:
                        raise TransientTraktError('Temporary Trakt Error: '+str(e))
                else:
                    raise TraktError('Trakt Error: '+str(e))

        response=json.loads(result)

        if 'status' in response and response['status']=='failure':
            if 'message' in response: raise TraktError(response['message'])
            if 'error' in response: raise TraktError(response['error'])
            else: raise TraktError()
        else:
            #log_utils.log('Trakt Response: %s' % (response), xbmc.LOGDEBUG)
            return response

