from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains  
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import NoSuchElementException   
from selenium.common.exceptions import ElementNotInteractableException
from selenium.common.exceptions import TimeoutException
import pandas as pd
import msvcrt, glob, random, requests

from lxml import html
import os, sys, time, datetime, re, math, csv, json, codecs, argparse, errno

from time import sleep
from enum import Enum
from os import listdir
from os.path import isfile, join

from lxml.html import fromstring
from itertools import cycle
import traceback

HEADLESS_MODE = True                                # Use the chrome browser without the graphical user interface (headless, recommended) 
USE_LOCAL_THUMBNAIL = True                          # Save the user avatars and photo thumbnails to disk for off-line viewing of html files
OUTPUT_DIR =  os.path.join(os.getcwd(), 'Output')   # at [current working directory]\Output

# mainly for a more realistic demonstration of progress on the console progress bar  
PHOTOS_PER_PAGE = 50             # 500px currently loads 50 photos per page
LOADED_ITEM_PER_PAGE = 50        # it also loads 50 followers, or friends, at a time in the popup window
NOTIFICATION_PER_LOAD = 20       # currently notifications are requested to display ( by scrolling the window) 20 items at a time

MAX_NOTIFICATION_REQUEST = 5000  # self limitation to avoid abusing
MAX_AUTO_LIKE_REQUEST = 100      # self limitation to avoid abusing
DEBUG = False


DATE_FORMAT = "%Y-%m-%d"                    # ex. 2019-06-15
DATETIME_FORMAT = "%Y-%b-%d--Time%H-%M-%S"  # ex. 2019-Jun-15--Time13-21-45

class user:
    """ Represents a user. It could be the main user(ie. me, the logged in user), or a target user whose photos we want to auto-like, or a user who had interaction with me(liked, commented, followed)
       
        - AVATAR_LOCAL : The full file name of the avatar image file, if we decide to save it on disk
        - FOLLOWING_STATUS is n/a for the main user, if not, it could be either "following" or "not follow"
    """
    def __init__(self, order = '', avatar_href = '', avatar_local = '', display_name = '', user_name = '', id = '0', number_of_followers = '0', following_status = ''):
        self.order = order
        self.avatar_href = avatar_href
        self.avatar_local = avatar_local
        self.display_name = display_name
        self.user_name = user_name
        self.id = id
        self.number_of_followers = number_of_followers
        self.following_status = following_status
    
    def to_dict(self):
        return {
            'No': self.order,
            'Avatar Href': self.avatar_href,
            'Avatar Local': self.avatar_local,
            'Display Name': self.display_name,
            'User Name': self.user_name,
            'ID': self.id,
            'Followers': self.number_of_followers,
            'Status': self.following_status
        }

class photo_stats:
    """ Photo statistics info.
        - TAGS is the comma-separated strings containing all tags set on the photo    
    """
    def __init__(self,  upload_date = '', views_count=0, votes_count=0, collections_count=0, comments_count=0, highest_pulse=0, rating=0, tags='' ):
        self.upload_date  = upload_date 
        self.views_count = views_count
        self.votes_count = votes_count 
        self.collections_count = collections_count
        self.comments_count = comments_count 
        self.highest_pulse = highest_pulse
        self.rating = rating
        self.tags = tags

class photo:
    """ Represent a photo info.

    - ORDER is the ascending number with the latest uploaded photo being 1
    - STATS is an object of type photo_stats()
    - THUMBNAIL_HREF is the link to the photo thumbnail
    - THUMBNAIL_LOCAL is the full file name of the thumbnail image, dowmloaded from the link thumbnail_href and saved on disk 
    - GALLERIES is a list containing the links to all the galleries that featured the photo
    """
    def __init__(self, author_name= '', order= '', id= '', title= '', href= '', thumbnail_href= '', thumbnail_local= '', galleries= '', stats= photo_stats()):
        self.author_name = author_name
        self.order = order  
        self.id = id
        self.title = title
        self.href = href
        self.thumbnail_href = thumbnail_href        
        self.thumbnail_local = thumbnail_local        
        self.galleries = galleries
        self.stats = stats

class notification:
    """ Represent a notification object.
        
        - ACTOR is an object of type user(), on which we will make use only 3 members: avatar_href, display_name, username
        - THIS_PHOTO is object of type photo(), on which we will make use only 3 members: photo_thumb, photo_link, photo_title
        - CONTENT is the type of notifications. It is 'liked', 'comment' or 'add to gallery'
        - TIMESTAMP is the time when the notification happened
        - STATUS is the following status of the main user toward the actor, ie. 'Following'  or 'Not follow'
        """
    def __init__(self, order, actor = user(), the_photo = photo(),  content = '', timestamp = '', status = ''): 
        self.order = order
        self.actor = actor
        self.content = content
        self.the_photo = the_photo        
        self.timestamp = timestamp
        self.status = status

class user_stats:
    """ Represent basic statistics of a user. Object of the class is considered mutabble and therefore can be passed as reference"""
    def __init__(self, display_name='', user_name='', id='', location='', affection_note='', following_note='', affections_count='', views_count='', 
                 followers_count='', followings_count='', photos_count='', galleries_count='', registration_date='', last_upload_date='', user_status=''):
        self.display_name = display_name
        self.user_name = user_name
        self.id = id
        self.location = location
        self.affection_note = affection_note
        self.following_note = following_note
        self.affections_count = affections_count
        self.views_count = views_count
        self.followers_count = followers_count
        self.followings_count = followings_count
        self.photos_count = photos_count
        self.galleries_count = galleries_count
        self.registration_date = registration_date
        self.last_upload_date = last_upload_date
        self.user_status = user_status

# not used for now
#class Output_file_type(Enum):
#   """ Enum representing 5 types of output list"""
#   NOT_DEFINED          = 0
#   FOLLOWERS_LIST       = 1                   
#   FOLLOWINGS_LIST      = 2                  
#   PHOTOS_LIST          = 3              
#   NOTIFICATIONS_LIST   = 4
#   UNIQUE_USERS_LIST    = 5        # Unique users with appearance count, extracted from Notifications list
#   STATISTICS_HTML_FILE = 6

class User_inputs():
    """ Represent the input entered by the user. 
    
    Choice is an character string representing available options: [1-13] or 'r','q' . The default value is zero which means commnand line arguments will not be used 
    """

    def __init__(self, use_command_line_args = False, choice='0', user_name='', password='', target_user_name='', photo_href='', gallery_href='', gallery_name='',
                 number_of_photos_to_be_liked=2 , index_of_start_photo=1, number_of_notifications=200, time_interval=3, index_of_start_user=1, number_of_users=100, csv_file=''):
        self.use_command_line_args          = use_command_line_args
        self.choice                         = choice
        self.user_name                      = user_name
        self.password                       = password
        self.target_user_name               = target_user_name
        self.photo_href                     = photo_href
        self.gallery_href                   = gallery_href
        self.gallery_name                   = gallery_name
        self.number_of_photos_to_be_liked   =  number_of_photos_to_be_liked
        self.index_of_start_photo           = index_of_start_photo
        self.number_of_notifications        = number_of_notifications
        self.time_interval                  = time_interval
        self.index_of_start_user            = index_of_start_user
        self.number_of_users                = number_of_users
        self.csv_file                       = csv_file

    def Reset(self):
        self.use_command_line_args = False
        self.choice                         = '0'
        self.user_name                      = ''
        self.password                       = ''
        self.target_user_name               = ''
        self.photo_href                     = ''
        self.gallery_href                   = ''
        self.gallery_name                   = ''
        self.number_of_photos_to_be_liked   =  2
        self.index_of_start_photo           = 1
        self.number_of_notifications        = 200
        self.time_interval                  = 3
        self.index_of_start_user            = 1
        self.number_of_users                = 100
        self.csv_file                       = ''

class Output_data():
    """ Represent all the output lists and data"""

    def __init__(self, output_dir = '', avatars_dir = '', thumbnails_dir = '', 
                 json_data = None, photos = None,notifications = None, unique_notificators = None, followers_list = None, followings_list = None, like_actioners_list= None, avatars_list=None, thumbnails_list=None):
        self.json_data = [] if json_data is None else json_data      
        self.photos = [] if photos is None else photos      
        self.notifications = [] if notifications is None else notifications      
        self.unique_notificators = [] if unique_notificators is None else unique_notificators      
        self.followers_list = [] if followers_list is None else followers_list      
        self.followings_list = [] if followings_list is None else followings_list     
        self.like_actioners_list = [] if like_actioners_list is None else like_actioners_list     
        #self.avatars_list = [] if avatars_list is None else avatars_list     
        #self.thumbnails_list = [] if thumbnails_list is None else thumbnails_list     
        self.stats = user_stats()  
        
        output_dir =  OUTPUT_DIR 
        os.makedirs(output_dir, exist_ok = True)
        self.output_dir = output_dir
        
        avatars_dir =  os.path.join(output_dir, 'avatars')
        os.makedirs(avatars_dir, exist_ok = True)
        self.avatars_dir = avatars_dir
        self.avatars_list = [f for f in listdir(avatars_dir) if isfile(join(avatars_dir, f))]
 
        thumbnails_dir =  os.path.join(output_dir, 'thumbnails')
        os.makedirs(thumbnails_dir, exist_ok = True)
        self.thumbnails_dir = thumbnails_dir
        self.thumbnails_list = [f for f in listdir(thumbnails_dir) if isfile(join(thumbnails_dir, f))]
 
    def Reset(self):
        self.json_data = None       
        self.photos =None        
        self.notifications = None   
        self.unique_notificators = None
        self.followers_list = None  
        self.followings_list = None 
        self.like_actioners_list= None
        self.stats = user_stats() 

# print colors text on console
def printR(text): print(f"\033[91m {text}\033[00m") #; logging.info(text)
def printG(text): print(f"\033[92m {text}\033[00m") #; logging.info(text)
def printY(text): print(f"\033[93m {text}\033[00m") #; logging.info(text)
def printC(text): print(f"\033[96m {text}\033[00m") #; logging.info(text) 
def printB(text): print(f"\033[94m {text}\033[00m") #; logging.info(text) 

#---------------------------------------------------------------
def Start_chrome_browser(options_list = [], headless_mode = True):
    """ use selenium webdriver to start chrome, with various options. Ex ["--start-maximized", "--log-level=3"] """

    chrome_options = Options()
    for option in options_list:
        chrome_options.add_argument(option)   
    chrome_options.add_argument('--log-level=3')   
    if headless_mode:
        print('Starting Chrome browser without the graphical user interface ...')
        chrome_options.add_argument("--headless") 
    else:
        printY('DO NOT INTERACT WITH THE CHROME BROWSER. IT IS CONTROLLED BY THE SCRIPT AND  WILL BE CLOSED WHEN THE TASK FINISHES')
        chrome_options.add_argument("--window-size=800,1000")
        #chrome_options.add_experimental_option("excludeSwitches", ['enable-automation']);   
    driver = webdriver.Chrome(options=chrome_options)
    return driver

#---------------------------------------------------------------
def Logged_in(driver):
    """ Check if any user is currently logged in the current session"""

    print('    Checking login status ...')
    # need to be in 500px domain
    if not '500px.com' in driver.current_url:
        driver.get('https://500px.com')
        time.sleep(1)

    body_ele = check_and_get_ele_by_tag_name(driver, 'body')
    # make sure the page body is rendered
    driver.execute_script("return document.body.innerHTML") 
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    if body_ele :
        body_text = body_ele.text
        return not 'Log in' in body_text
    else:
        return true

#---------------------------------------------------------------
def Close_chrome_browser(chrome_driver):
    """ Close the chrome browser, care-free of exceptions. """
    if chrome_driver is None:
        return
    try:
        chrome_driver.close()
    except WebDriverException:
        pass

#---------------------------------------------------------------
def Create_user_statistics_html(stats):
    """ write user statistic object stats to an html file. """
    if stats is None:
        return

    time_stamp = datetime.datetime.now().replace(microsecond=0).strftime(DATETIME_FORMAT)

    output = f'''
<html>\n\t<body>
        <h2>User statistics</h2>
        <p>Date: {time_stamp}</p>
        <table>
            <tr>                <td><b>User name</b></td>           <td>{stats.user_name}</td>\n</tr>
            <tr>                <td><b>Display name</b></td>        <td>{stats.display_name}</td>\n</tr>
            <tr>                <td><b>Id</b></td>                  <td>{stats.id}</td>\n</tr>
            <tr>                <td><b>Location</b></td>            <td>{stats.location}</td>\n</tr>
            <tr>                <td><b>Activities</b></td>          <td>{stats.affection_note}</td>\n</tr>
            <tr>                <td> </td>                          <td>{stats.following_note}</td>\n</tr>
            <tr>                <td><b>Affections</b></td>          <td>{stats.affections_count}</td>\n</tr>
            <tr>                <td><b>Views</b></td>               <td>{stats.views_count}</td>\n</tr>
            <tr>                <td><b>Followers</b></td>           <td>{stats.followers_count}</td>\n</tr>
            <tr>                <td><b>Followings</b></td>          <td>{stats.followings_count}</td>\n</tr>
            <tr>                <td><b>Photos count</b></td>        <td> {stats.photos_count}</td>\n</tr>
            <tr>                <td><b>Galleries count</b></td>     <td>{stats.galleries_count}</td>\n</tr>
            <tr>                <td><b>Registration date</b></td>   <td>{stats.registration_date}</td>\n</tr>
            <tr>                <td><b>Last upload date</b></td>    <td>{stats.last_upload_date}</td>\n</tr>
            <tr>                <td><b>User status</b></td>         <td>{stats.user_status}</td>\n</tr>
        <table>\n\t<body>\n<html>
'''
    return output

#---------------------------------------------------------------
def Write_photos_list_to_csv(user_name, list_of_photos, csv_file_name):
    """ Write photos list to a csv file with the given  name. Return True if success.    
        If the file is currently open, give the user a chance to close it and come back to re-try.   
    """
    try:
        with open(csv_file_name, 'w', encoding = 'utf-16', newline='') as csv_file:
            writer = csv.writer(csv_file)
            writer = csv.DictWriter(csv_file, fieldnames = ['No', 'ID', 'Photo Title', 'Href', 'Thumbnail Href', 'Thumbnail Local', 'Views', 'Likes', 'Comments', 'Featured In Galleries', 'Highest Pulse', 'Rating', 'Date', 'Tags'])  
            writer.writeheader()
            for i, a_photo in enumerate(list_of_photos):
                writer.writerow({'No' : str(a_photo.order), 'ID': str(a_photo.id), 'Photo Title' : str(a_photo.title), 'Href' :a_photo.href, 'Thumbnail Href': a_photo.thumbnail_href, \
                                 'Thumbnail Local' : a_photo.thumbnail_local, 'Views': str(a_photo.stats.views_count), 'Likes': str(a_photo.stats.votes_count), 'Comments': str(a_photo.stats.comments_count), \
                                 'Featured In Galleries': str(a_photo.galleries), 'Highest Pulse': str(a_photo.stats.highest_pulse), 'Rating': str(a_photo.stats.rating), \
                                 'Date': str(a_photo.stats.upload_date), 'Tags': a_photo.stats.tags}) 
            printG(f"List of {user_name}\'s {len(list_of_photos)} photo is saved at:\n {os.path.abspath(csv_file_name)}")
        return True

    except PermissionError:
        printR(f'Error writing file {os.path.abspath(csv_file_name)}.\nMake sure the file is not in use. Then type r for retry >')
        retry = input()
        if retry == 'r': 
            Write_photos_list_to_csv(user_name, list_of_photos, csv_file_name)
        else:
            printR('Error witing file' + os.path.abspath(csv_file_name))
            return False

#---------------------------------------------------------------
def Write_users_list_to_csv(users_list, csv_file_name):
    """ Write the users list to a csv file with the given  name. Return True if success.h
    
    The users list could be one of the following: followers list, friends list or unique users list. 
    If the file is currently open, give the user a chance to close it and come back to retry
    """
    try:
        with open(csv_file_name, 'w', encoding = 'utf-16', newline='') as csv_file:  # could user utf-16be
            writer = csv.writer(csv_file)
            writer = csv.DictWriter(csv_file, fieldnames = ['No', 'Avatar Href', 'Avatar Local', 'Display Name', 'User Name', 'ID', 'Followers', 'Status'])  
            writer.writeheader()
            for a_user in users_list:
                writer.writerow({'No' : a_user.order, 'Avatar Href': a_user.avatar_href,'Avatar Local': a_user.avatar_local, 'Display Name' : a_user.display_name, \
                    'User Name': a_user.user_name, 'ID': a_user.id, 'Followers': a_user.number_of_followers, 'Status': a_user.following_status}) 
        printG('The users list is saved at:\n ' + os.path.abspath(csv_file_name) )
        return True
    except PermissionError:
        retry = input(f'Error writing to file {csv_file_name}. Make sure the file is not in use. Then type r for retry >')
        if retry == 'r': 
            Write_users_list_to_csv(users_list, csv_file_name)
        else:
            printG('Error writing file\n' + os.path.abspath(csv_file_name))
            return False 

#---------------------------------------------------------------
def Write_notifications_to_csvfile(notifications_list, csv_file_name):
    """ Write the  notifications list to a csv file with the given  name. Return True if success.
        If the file is currently open, give the user a chance to close it and come back to retry

    Headers: 1   2            3             4             5          6   7        8                     9                      10           11          12      13
             No, Avatar Href, Avatar Local, Display Name, User Name, ID, Content, Photo Thumbnail Href, Photo Thumbnail Local, Photo Title, Time Stamp, Status, Photo Link
    """

    try:
        with open(csv_file_name, 'w', encoding = 'utf-16', newline='') as csv_file:
            writer = csv.writer(csv_file)
            writer = csv.DictWriter(csv_file, fieldnames = ['No', 'Avatar Href', 'Avatar Local', 'Display Name', 'User Name', 'ID', 'Content', \
                'Photo Thumbnail Href', 'Photo Thumbnail Local', 'Photo Title', 'Time Stamp', 'Status', 'Photo Link'])    
            writer.writeheader()
            for notif in notifications_list:
                writer.writerow({'No': notif.order, 'Avatar Href' : notif.actor.avatar_href, 'Avatar Local': notif.actor.avatar_local, \
                                 'Display Name': notif.actor.display_name, 'User Name': notif.actor.user_name, 'ID' : notif.actor.id, \
                                 'Content': notif.content, 'Photo Thumbnail Href': notif.the_photo.thumbnail_href, 'Photo Thumbnail Local': notif.the_photo.thumbnail_local, \
                                 'Photo Title': notif.the_photo.title, 'Time Stamp': notif.timestamp, 'Status': notif.status, 'Photo Link': notif.the_photo.href}) 
        printG('Notifications list is saved at:\n ' + os.path.abspath(csv_file_name))
        return True 
    except PermissionError:
        retry = input(f'Error writing to file {csv_file_name}.\n Make sure the file is not in use, then type r for retry >')
        if retry == 'r':  
            Write_notifications_to_csvfile(notifications_list, csv_file_name)
        else: 
            printR(f'Error writing file {csv_file_name}')
            return False

#---------------------------------------------------------------
def Write_unique_notificators_list_to_csv(unique_users_list, csv_file_name):
    """ Write the unique notifications list to a csv file with the given  name. Return True if success.   
    If the file is currently open, give the user a chance to close it and come back to retry
    
    Headers:    0   1            2             3             4          5   6
                No, Avatar Href, Avatar Local, Display Name, User Name, ID, Count
    """
    try:
        with open(csv_file_name, 'w', encoding = 'utf-16', newline='') as csv_file:
            writer = csv.writer(csv_file)
            writer = csv.DictWriter(csv_file, fieldnames = ['No', 'Avatar Href', 'Avatar Local', 'Display Name', 'User Name', 'ID', 'Count'])  
            writer.writeheader()

            for actor in unique_users_list:
                items = actor.split(',')
                if len(items) == 7:
                    writer.writerow({'No': items[0], 'Avatar Href': items[1], 'Avatar Local': items[2], 'Display Name': items[3], 'User Name': items[4], 'ID' : items[5], 'Count': items[6]}) 
            printG('Unique notificators is saved at:\n ' + os.path.abspath(csv_file_name))
            return True 

    except PermissionError:
        retry = input(f'Error writing to file {csv_file_name}. Make sure the file is not in use. Then type r for retry >')
        if retry == 'r': 
            Write_unique_notificators_list_to_csv(unique_users_list, csv_file_name)
        else: 
            printR(f'Error writing file {csv_file_name}')
            return False

#---------------------------------------------------------------
def Hover_element_by_its_xpath(driver, xpath):
    """ hover the mouse on an element specified by the given xpath. """
    element = check_and_get_ele_by_xpath(driver, xpath)
    if element is not None:
        hov = ActionChains(driver).move_to_element(element)
        hov.perform()

#---------------------------------------------------------------
def Hover_by_element(driver, element):
    """ Hover the mouse over a given element. """               
    #element.location_once_scrolled_into_view
    hov = ActionChains(driver).move_to_element (element)
    hov.perform()

#---------------------------------------------------------------
def Get_element_text_by_xpath(page, xpath_string):
    """Return the text of element, specified by the element xpath. Return '' if element not found. """
    if page is None or not xpath_string:
        return ''
    ele = page.xpath(xpath_string)
    if ele is not None and len(ele) > 0 : 
        return ele[0].text
    return ''

#---------------------------------------------------------------
def Get_element_attribute_by_ele_xpath(page, xpath, attribute_name):
    """Get the value of the given attribute name, at the element of the given xpath. Return '' if element not found."""
    if page is None or not xpath or not attribute_name:
        return ''
    ele = page.xpath(xpath)
    time.sleep(1)
    if ele is not None and len(ele) > 0:
        try:
            return ele[0].attrib[attribute_name] 
        except:
            printR(f'Error getting attribute {attribute_name}')
    return ''

#---------------------------------------------------------------
def check_and_get_ele_by_xpath(element, xpath):
    """ Find the web element from a given xpath, return none if not found.
    
    The search can be limited within a given web element, or the whole document if the browser driver is passed instead of the web element
    """
    if element is None or not xpath:
        return  None
    try:
        return element.find_element_by_xpath(xpath)
    except NoSuchElementException:
        return None

#---------------------------------------------------------------
def check_and_get_all_elements_by_xpath(element, xpath):
    """ Find the web elements from a given xpath, return none if not found.
    
    The search can be limited within a given web element, or the whole document if the browser driver is passed instead of the web element
    """
    if element is None or not xpath:
        return  []
    try:
        return element.find_elements_by_xpath(xpath)
    except NoSuchElementException:
        return []
#---------------------------------------------------------------
def check_and_get_ele_by_class_name(element, class_name):
    """Find the web element of a given class name, return none if not found.
    
    The search can be limited within a given web element, or the whole document if the browser driver is passed instead of the web element
    """
    if element is None or not class_name:
        return None 
    try:
        return element.find_element_by_class_name(class_name) 
    except NoSuchElementException:
        return None

#---------------------------------------------------------------
def check_and_get_ele_by_id(element, id_name):
    """Find the web element of a given id, return none if not found.

    The search can be limited within a given web element, or the whole document if the browser driver is passed instead of the web element
    """
    if element is None or not id_name:
        return  None 
    try:
        return element.find_element_by_id(id_name) 
    except NoSuchElementException:
        return None

#---------------------------------------------------------------
def check_and_get_ele_by_tag_name(element, tag_name):
    """Find the web element of a given tag name, return none if not found.

    THE SEARCH CAN BE LIMITED WITHIN A GIVEN WEB ELEMENT, OR THE WHOLE DOCUMENT, BY PASSING THE BROWSER DRIVER
    """
    if element is None or not tag_name:
        return None   
    try:
        return element.find_element_by_tag_name(tag_name) 
    except NoSuchElementException:
        return None


#---------------------------------------------------------------
def check_and_get_all_elements_by_tag_name(element, tag_name):
    """Find all the web elements of a given tag name, return empty list if tag_name not found.

    The search can be limited within a given web element, or the whole document if the browser driver is passed instead of the web element
    """
    if element is None or not tag_name:
        return []
    try:
        return element.find_elements_by_tag_name(tag_name) 
    except NoSuchElementException:
        return []

#---------------------------------------------------------------
def check_and_get_all_elements_by_class_name(element, class_name):
    """Find all the web elements of a given class name, return empty list if class_name not found.

    The search can be limited within a given web element, or the whole document if the browser driver is passed instead of the web element
    """
    if element is None or not class_name:
        return []
    try:
        return element.find_elements_by_class_name(class_name) 
    except NoSuchElementException:
        return []

#---------------------------------------------------------------
def check_and_get_ele_by_css_selector(element, selector):
    """Find the web element of a given css selector, return none if not found.

    The search can be limited within a given web element, or the whole document if the browser driver is passed instead of the web element
    """
    if element is None or not selector:
        return None  
    try:
        return element.find_element_by_css_selector(selector)
    except NoSuchElementException:
        return None

#---------------------------------------------------------------
def check_and_get_all_elements_by_css_selector(element, selector):
    """Find the web elements of a given css selector, return none if not found.

    The search can be limited within a given web element, or the whole document if the browser driver is passed instead of the web element
    """
    if element is None or not selector:
        return  [] 
    try:
        return element.find_elements_by_css_selector(selector)
    except NoSuchElementException:
        return []

#---------------------------------------------------------------
def Get_web_ele_text_by_xpath(element_or_driver, xpath):
    """ Use WebDriver function to find text from a given xpath, return empty string if not found.
    
    Use absolute xpath if the driver is passed
    Use relative xpath if an web element is passed
     """
    if element_or_driver is None or not xpath:
        return ''
    try:
        ele = element_or_driver.find_element_by_xpath(xpath)
        if ele is not None:
            return ele.text       
    except NoSuchElementException:
        return ''

#---------------------------------------------------------------
def GetUploadDate(driver, photo_link):
    """Given a photo link, returns the photo upload date or time. """

    driver.get(photo_link)
    last_photo_page_HTML = driver.execute_script("return document.body.innerHTML") 
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    page = html.document_fromstring(last_photo_page_HTML)
    p = page.xpath('//*[@id="root"]/div[4]/div/div[2]/div[3]/div[1]/div[2]/p/span')

                    
    if len(p) > 0:
        return p[0].text_content() 
    else: 
       return "not found" 

#---------------------------------------------------------------
def Open_user_home_page(driver, user_name):
    """Open the home page of a given user and wait for the page to load. If the user page is not found or timed out (30s),
       return False and the error message. If not, return True and a blank message """ 
    if driver is None or not user_name:
        return
    print(f"    Open {user_name}'s home page ...")   

    driver.get('https://500px.com/' + user_name)
    # waiting until the page is opened
    main_window_handle = None
    time_out = 30
    count_down = time_out
    while not main_window_handle and count_down > 0:
        main_window_handle = driver.current_window_handle
        count_down -= 1
    if count_down <=0:
        return False, f"Timed out ({time_out}s) while opening {user_name}'s home page. Please retry"

    if check_and_get_ele_by_class_name(driver, 'not_found') is None and \
       check_and_get_ele_by_class_name(driver, 'missing') is None:
        return True, ''
    else:
        #Close_chrome_browser(driver)
        return False, f'Error reading {user_name}\'s page. Please make sure a valid user name is used'

#---------------------------------------------------------------
def Finish_Javascript_rendered_body_content(driver, time_out=10, class_name_to_check='', css_selector_to_check='', xpath_to_check=''):
    """ Run the Javascript to render the body content. Log error if it happened. Return:
        1) The fail/success status, 
        2) The page content text 
           
    The completion of the js script, within a given timeout, is determined by checking the existance of one of the given elements. 
    Element to check is one of the following: class_name, css_selector, xpath, prioritied by this order
    """

    innerHtml = driver.execute_script("return document.body.innerHTML")  
    
    try:
        if class_name_to_check:
            element = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.CLASS_NAME, class_name_to_check)))
        elif css_selector_to_check:
            element = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.CSS_SELECTOR, css_selector_to_check)))
        elif xpath_to_check:
            element = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.XPATH, xpath_to_check)))
        else:
            printR('Internal error. No identifier was given for detecting the page loading completion ')
            return False, ''
    except TimeoutException :
        printR(f'Time out {time_out}s while loading. Please retry.')
        return False, '', 
    except:
        printR('Error loading. Please retry.')
        return False, ''   
    
    return True, innerHtml
#---------------------------------------------------------------


def Get_stats(driver, user_inputs, output_lists):
    """Get statistics of a given user: number of likes, views, followers, following, photos, last upload date...
       If success, return statistics object and a blank message. If not return None and the error message

       Process:
       - Open user home page https://500px.com/[user_name]
       - Run the document javascript to render the page content
       - Use lxml to extract interested data
       - Use regular expression to extract the json part in the body, and obtain more data from it.
    """

    success, message = Open_user_home_page(driver, user_inputs.user_name)
    if not success:
        if message.find('Error reading') != -1:
            user_inputs.user_name = ''
        return None, message
        
    Hide_banners(driver)
  
    # abort the action if the target objects failed to load within a given timeout
    success, innerHtml = Finish_Javascript_rendered_body_content(driver, time_out=30, class_name_to_check='finished')
    if not success:
        return None, f"Error loading user {user_inputs.user_name}'s photo page"
    # using lxml for html handling
    page = html.document_fromstring(innerHtml)

    # Affection note
    affection_note = Get_element_attribute_by_ele_xpath(page, "//li[@class='affection']", 'title' )
    # Following note
    following_note = Get_element_attribute_by_ele_xpath(page, "//li[@class='following']", 'title' )
    # Views count
    views_ele = check_and_get_ele_by_class_name(driver,'views' )
    if views_ele is not None:
        ele =  check_and_get_ele_by_tag_name(views_ele,'span')
        if ele is not None:
            views_count= ele.text

    # Location
    location =  Get_element_text_by_xpath(page,'//*[@id="content"]/div[1]/div[4]/ul/li[5]')
    loc_test = check_and_get_all_elements_by_class_name(driver, 'location')

    #using regex to extract from the javascript-rendered html the json part that holds user data 
    # Jul 26 2019: modification due to page structure changes: photos list is no longer included in userdata
    #   userdata = re.findall('"userdata":(.*),"viewer":', innerHtml)
    i = innerHtml.find('"userdata":') 
    j = innerHtml.find('</script>', i)
    userdata = innerHtml[i + 11 : j - 2]
    if len(userdata) == 0:
       return None, 'Error getting the user data'
    
    json_data = json.loads(userdata)
    print("    Getting the last upload date ...")
    last_photo_href = Get_element_attribute_by_ele_xpath(page, './/*[@id="content"]/div[3]/div/div/div[1]/a', 'href')
    if not last_photo_href:
        #printR('Error getting the last photo href')
        return None, '    Error getting the last photo href'

    driver.get(r'https:/500px.com' + last_photo_href)
    time_out = 30
    try:  
        info_box = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.XPATH, '//*[@id="root"]/div[3]/div/div[2]')) )
    except  TimeoutException:
        #printR(f'Time out ({time_out}s)! Please try again')
        return None, f'Time out ({time_out}s)! Please try again'

    last_upload_date = ''
    upload_date_ele = check_and_get_ele_by_xpath(info_box,  '//div[1]/div[2]/p/span')        
    if upload_date_ele is None:
        upload_date_ele = check_and_get_ele_by_xpath(info_box, '//div[3]/div[1]/div/p/span') 

    if upload_date_ele is not None:
        last_upload_date = upload_date_ele.text
 
    active_int = json_data['active'] 
    if   active_int == 0 : user_status = 'Not Active'
    elif active_int == 1 : user_status = 'Active'
    elif active_int == 2 : user_status = 'Deleted by user'
    elif active_int == 3 : user_status = 'Banned'

    # write to file the userdata in json for debugging
    if DEBUG:
        jason_string = json.dumps(json_data, indent=2, sort_keys=True) 
        time_stamp = datetime.datetime.now().replace(microsecond=0).strftime("%Y_%m_%d__%H_%M_%S")
        Write_string_to_text_file(jason_string, os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_stats_json_{time_stamp}.txt'))

    stats = user_stats(json_data['fullname'], user_inputs.user_name, json_data['id'], location, 
                       affection_note, following_note, json_data['affection'], views_count, json_data['followers_count'], json_data['friends_count'], 
                       json_data['photos_count'], json_data['galleries_count'], json_data['registration_date'][:10], last_upload_date, user_status)
    return stats, ''
      
#---------------------------------------------------------------

def Get_photos_list(driver, user_inputs, output_lists):
    """Return the list of photos from a given user.

    Process: 
    - Open user home page, scroll down until all photos are loaded
    - Make sure the document javascript is called to get the full content of the page
    - Extract photo data: no, id, photo title, href, thumbnail, views, likes, comments, galleries, highest pulse, rating, date, tags
    """

    photos_list = []
    success, message = Open_user_home_page(driver, user_inputs.user_name)
    if not success:
        if message.find('Error reading') != -1:
            user_inputs.user_name = ''
        return [], message

    Hide_banners(driver)

    # We intend to scroll down an indeterminate number of times until the end is reached
    # In order to have a realistic progress bar, we need to give an estimate of the number of scrolls needed
    estimate_scrolls_needed = 3  #default value, just in case
    photos_count  = 1
    photos_count_ele = check_and_get_ele_by_css_selector(driver, '#content > div.profile_nav_wrapper > div > ul > li.photos.active > a > span')
    if photos_count_ele is not None:
        photos_count = int(photos_count_ele.text.replace('.', '').replace(',', ''))
        estimate_scrolls_needed =  math.floor( photos_count / PHOTOS_PER_PAGE) +1

    Scroll_to_end_by_class_name(driver, 'photo_link', photos_count)
    
    # abort the action if the target objects failed to load within a given timeout
    success, innerHtml = Finish_Javascript_rendered_body_content(driver, time_out=15, class_name_to_check='finished')
    if not success:
        return [], f"Error loading user {user_inputs.user_name}'s photo page"

    #if DEBUG:
    #     Write_string_to_text_file(str(innerHtml.encode('utf-8')), user_inputs.user_name + '_innerHTML.txt')
    page = html.document_fromstring(innerHtml)

    #extract photo title and href (alt tag) using lxml and regex
    els = page.xpath("//a[@class='photo_link ']")  
    img_ele = page.xpath("//img[@data-src='']")
    num_item = len(els)
    if num_item == 0:
        return [], f'User {user_name} does not upload any photo'

    update_progress(0, f'    - Extracting 0/{num_item} photos:')

    # Create the photos list
    for i in range(num_item): 
        update_progress(i / (num_item -1), f'    - Extracting  {i + 1}/{num_item} photos:')
        # reset variables
        photo_id, title, photo_thumbnail_href, photo_thumbnail_local = '', '0', '', ''
        
        # get photo link, 
        photo_href = r'https://500px.com' + els[i].attrib["href"]

        # photo id
        photo_id  =  re.search('\/photo\/(\d+)', photo_href).group(1)

        # title and thumbnail 
        if i < len(img_ele):
            title = img_ele[i].attrib["alt"]

            photo_thumbnail_href = img_ele[i].attrib["src"]
            # save the photo thumbnail to disk
            if USE_LOCAL_THUMBNAIL:
                photo_thumbnail_local = photo_id + '.jpg'
                if not photo_thumbnail_local in  output_lists.thumbnails_list:
                    #time.sleep(random.randint(5, 10) / 10)  
                    photo_thumbnail_local = Save_photo_thumbnail(photo_thumbnail_href, output_lists.thumbnails_dir )

        # open each photo page to get photo statistics
        time_out = 40
        id = ''
        galleries_list = []
        order = i + 1        
        try:  
            driver.get(photo_href)
            time.sleep(random.randint(1, 5) / 10)
            info_box = WebDriverWait(driver, time_out).until(EC.visibility_of_element_located((By.XPATH, '//*[@id="root"]/div[3]/div/div[2]')) )
        except  TimeoutException:
            # log error, add whatever available of the photo, then jumpt to the next photo
            printR(f'Time out ({time_out}s). Ignoring photo #{i + 1}, {title}!' )
            photos_list.append(photo(user(), id = photo_id, title = title, thumbnail_href = photo_thumbnail_href, thumbnail_local = photo_thumbnail_local, stats = photo_stats() ) )
            continue

        # --------------------------------------------
        # We can use either selenium, or selenium + regular expression to achieve some tasks below. I keep both options here for evaluating the performance
        USING_REGULAR_EXPRESSION = False
 
        if USING_REGULAR_EXPRESSION :
            # uploade date
            info_box_text = info_box.text
            upload_date  =  re.search('Calendar.*\n(.*)', info_box_text)
            upload_date = '' if upload_date is None else str.strip(upload_date.group(1))        
            if upload_date and ('ago' not in upload_date):
                try:
                    dt = datetime.datetime.strptime(upload_date, "%b %d, %Y")
                    upload_date = dt.strftime("%Y %m %d")
                except:
                    # if error occured, write what are available sofar before jumping to the next photo
                    printR(f'Error converting date-time string: {upload_date}, on photo: {title}')
                    this_photo = photo(user(user_name=user_inputs.user_name), order=order, id='', title=title, href=photo_href, thumbnail=photo_thumbnail_href, galleries='', stats = photo_stats() )      
                    photos_list.append(this_photo)
                    continue

            votes_count = re.search(r'Created with Sketch.*\n(.*)', info_box_text)
            votes_count = '' if votes_count is None else str.strip(votes_count.group(1)).replace(',','').replace('.','')

            highest_pulse  = re.search(r'Pulse\s*\n(.*)', info_box_text)      
            highest_pulse = '' if highest_pulse is None else str.strip(highest_pulse.group(1))
            
            views_count  =   re.search(r'Views\s*\n(.*)', info_box_text)  
            views_count = '' if views_count is None else str.strip(views_count.group(1)).replace(',','').replace('.','')

            # comments count
            comments_count =  Get_web_ele_text_by_xpath(info_box, '//div/div[4]/div[2]/div/h4').split(' ')[0]  

            # TODO: include category in the photo object
            #category  =  re.search(r'Category(.*)', info_box_text)      
            #category = '' if category is None else str.strip(category.group(1))

            # list of tags
            tags = []
            try:
                # regexp depends on whether user logged in or not:
                if user_inputs.password is '':
                    tags = re.search(r'Category.*\n(.*)', info_box_text, re.DOTALL).group(0).split('\n')
                    tags.pop(0)
                else:
                    tags = re.search(r'Category.*\n(.*)\nFeatured in these galleries', info_box_text, re.DOTALL).group(0).split('\n')
                    tags.pop(0)
                    tags.pop()
                tags.sort()
            except:
                printR(f'Error on getting tags for photo {title}')
                pass

            # get galleries list, if user logged in
            if user_inputs.password is not '':
                view_all_ele = driver.find_elements_by_xpath("//*[contains(text(), 'View all')]")
                if len(view_all_ele) == 0 or (len(view_all_ele) == 1 and view_all_ele[0].tag_name == 'script'):
                    collections_count = 0
                else:
                    view_all_ele[0].location_once_scrolled_into_view
                    view_all_ele[0].click()         
                    time.sleep(1)
                    eles = driver.find_elements_by_class_name('ant-modal-body')       
                    galleries_count = 0

                    if len(eles)> 0:
                        containers = check_and_get_all_elements_by_xpath(eles[0],'./div/div')
                        if containers is not None and len(containers)> 0:
                            childs =  check_and_get_all_elements_by_xpath(containers[0], './div') #containers[0].find_elements_by_xpath("./div")
                            if childs is not None:
                                galleries_count = len(childs)
                                for child in childs:
                                    a_ele = check_and_get_ele_by_tag_name(child, 'a')
                                    if a_ele is  not None:
                                        galleries_list.append(a_ele.get_attribute('href'))

        # using selenium ----------------------------------------
        else:
            #upload date
            upload_date = Get_web_ele_text_by_xpath(info_box, '//div[3]/div[1]/div/p/span' )
            if upload_date and ('ago' not in upload_date):
                try:
                    dt = datetime.datetime.strptime(upload_date, "%b %d, %Y")
                    upload_date = dt.strftime("%Y %m %d")
                except:
                    printR(f'Error converting date-time string: {upload_date}, on photo: {title}')
                    this_photo = photo(user(user_name = user_inputs.user_name), order = order, id = photo_id, title = title, href = photo_href, 
                                       thumbnail_href = photo_thumbnail_href, thumbnail_local = photo_thumbnail_local, galleries='', stats = photo_stats() )      
                    photos_list.append(this_photo)
                    continue

            #views count
            views_count =  Get_web_ele_text_by_xpath(info_box, '//div/div[2]/div[3]/div[3]/div[2]/h3/span').replace(',','').replace('.','')      
                                          
            # highest pulse
            highest_pulse =  Get_web_ele_text_by_xpath(info_box, '//div/div[2]/div[3]/div[3]/div[1]/h3') 
        
            # Get votes (likes) count
            try:
                photo_likes_count_ele = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.XPATH, '//a[@data-id="photo-likes-count"]')) )
            except  TimeoutException:
                 
                # log error, add whatever available of the photo, then jumpt to the next photo
                printR(f'Time out ({time_out}s). Ignoring photo #{i + 1}, {title}!' )
                photos_list.append(photo(user(), id = photo_id, title = title, thumbnail_href = photo_thumbnail_href, thumbnail_local = photo_thumbnail_local, 
                                         stats = photo_stats(upload_date = upload_date, views_count = views_count, highest_pulse = highest_pulse) ) )
                continue

            votes_count = photo_likes_count_ele.text.replace(',','').replace('.','')

            # comments count
            comments_count =  Get_web_ele_text_by_xpath(info_box, '//div/div[4]/div[2]/div/h4').split(' ')[0].replace(',','').replace('.','')

            #tags
            tags = []
            container =  check_and_get_ele_by_xpath(info_box, '//div/div[2]/div[3]/div[6]')
            if container is not None:
                a_eles = check_and_get_all_elements_by_tag_name(container, 'a')
                if a_eles is not None:
                    for item in a_eles:
                        tag = item.text                  
                        if tag is not '': tags.append(tag)
                    tags.sort()

            # get galleries list, if user logged in
            if user_inputs.password is not '':
                view_all_ele = driver.find_elements_by_xpath("//*[contains(text(), 'View all')]")
                if len(view_all_ele) == 0 or (len(view_all_ele) == 1 and view_all_ele[0].tag_name == 'script'):
                    collections_count = 0
                else:
                    view_all_ele[0].location_once_scrolled_into_view
                    view_all_ele[0].click()         
                    time.sleep(1)
                    eles = driver.find_elements_by_class_name('ant-modal-body')       
                    galleries_count = 0

                    if len(eles)> 0:
                        containers = check_and_get_all_elements_by_xpath(eles[0],'./div/div')
                        if containers is not None and len(containers)> 0:
                            childs =  check_and_get_all_elements_by_xpath(containers[0], './div') 
                            if childs is not None:
                                galleries_count = len(childs)
                                for child in childs:
                                    a_ele = check_and_get_ele_by_tag_name(child, 'a')
                                    if a_ele is  not None:
                                        galleries_list.append(a_ele.get_attribute('href'))

        # --------------------------------------------
        # common section for both section
        statistics = photo_stats(upload_date = upload_date, views_count = views_count, votes_count = votes_count, collections_count = 0, 
                                 comments_count = comments_count, highest_pulse = highest_pulse,rating = 0, tags = ",".join(tags) )
 
        this_photo = photo(user(user_name = user_inputs.user_name), order = order, id = photo_id, title = title, href = photo_href, 
                           thumbnail_href = photo_thumbnail_href, thumbnail_local = photo_thumbnail_local, galleries = ",".join(galleries_list), stats = statistics )      

        photos_list.append(this_photo)

    return photos_list, ''

#---------------------------------------------------------------

def Get_followers_list(driver, user_inputs, output_lists):
    """Get the list of users who follow me. Info for each item in the list are: 
       No, Avatar Href, Avatar Local, Display Name, User Name, ID, Followers, Status
       If logged in, we can extract my following status to each of my followers  ( whether or not I'm alse following my follower)  
    Process:
    - Open the user home page, locate the text "followers" and click on it to open the modal windonw that hosts the followers list
    - Scroll to the end for all items to be loaded
    - Make sure the document js is running for all the data to load in the page body
    - Extract info and put in a list. 
    - Return the list
    """

    followers_list = []   
    if driver.current_url != 'https://500px.com/' + user_inputs.user_name:
        success, message = Open_user_home_page(driver, user_inputs.user_name)
        if not success:
            printR(message)
            if message.find('Error reading') != -1:
                user_inputs.user_name = ''
            return followers_list

    Hide_banners(driver)
    # click on the Followers text to open the modal window
    ele = check_and_get_ele_by_class_name(driver, "followers")    
    if ele is None:
        printR('Error on getting the followers list')
        return followers_list
    else:
        ele.click()

    # abort the action if the target objects failed to load within a given timeout
    if not Finish_Javascript_rendered_body_content(driver, time_out=30, class_name_to_check='actors')[0]:
        return followers_list

    # extract number of followers                 
    followers_ele = check_and_get_ele_by_xpath(driver, '//*[@id="modal_content"]/div/div/div/div/div[1]/span')
    if followers_ele is None:
        printF('Error while getting the number off followers')
        return followers_list

    # remode thousand-separator character, if existed
    followers_count = int(followers_ele.text.replace(",", "").replace(".", ""))
    print(f'    User {user_inputs.user_name} has {str(followers_count)} follower(s)')

    # keep scrolling the modal window (LOADED_ITEM_PER_PAGE items are loaded at a time), until the end, where the followers count is reached 
    iteration_num = math.floor(followers_count / LOADED_ITEM_PER_PAGE) + 1 
           
    for i in range(1, iteration_num + 1):
        update_progress(i / (iteration_num), f'    - Scrolling down to load all followers {i}/{iteration_num + 1}:')
        index_of_last_item_on_page = i * LOADED_ITEM_PER_PAGE -1
        try:
            last_ele = check_and_get_ele_by_xpath(driver, '//*[@id="modal_content"]/div/div/div/div/div[2]/ul/li[' + str(index_of_last_item_on_page) + ']')            
            if last_ele is not None:
                last_ele.location_once_scrolled_into_view
                time.sleep(random.randint(10, 20) / 10)  
        except NoSuchElementException:
            printR('Error while scrolling down to load more item')
            pass

    # now that we have all followers loaded, start extracting the info
    update_progress(0, f'    - Extracting data 0/{followers_count}:')

    # abort the action if the target objects failed to load within a given timeout
    if not Finish_Javascript_rendered_body_content(driver, time_out=30, class_name_to_check='finished')[0]:
        return followers_list

    actor_infos = driver.find_elements_by_class_name('actor_info')
    actors_following =  driver.find_elements_by_css_selector('.actor.following')
    len_following = len(actors_following)

    lenght = len(actor_infos)

    for i, actor_info in enumerate(actor_infos):
        if i > 0:
            update_progress( i / (len(actor_infos) - 1), f'    - Extracting data {i + 1}/{followers_count}:')

        user_name, display_name, follower_page_link, following_status = '', '', '', ''
        count = ' '
  
        try:
            # get user name 
            name_ele = check_and_get_ele_by_class_name(actor_info, 'name')  
            if name_ele is not None:
                follower_page_link = name_ele.get_attribute('href')
                user_name = follower_page_link.replace('https://500px.com/', '')
            
            # get user avatar, user id and save the user avatar image to disk
            avatar_href, avatar_local, user_id = '', ' ', '0'
            actor_parent_ele = check_and_get_ele_by_xpath(actor_info, '..')   
            if actor_parent_ele is not None:
                avatar_ele = check_and_get_ele_by_class_name(actor_parent_ele, 'avatar')
                if avatar_ele is not None:
                    style = avatar_ele.get_attribute('style')
                    avatar_href =  style[style.find('https'): style.find('\")')]
  
                    # if user has default avatar
                    if 'userpic.png' in avatar_href:
                        if USE_LOCAL_THUMBNAIL:
                            avatar_local = 'userpic.png'
                    else:
                        user_id  =  re.search('\/user_avatar\/(\d+)\/', avatar_href).group(1)
                        avatar_local = user_id + '.jpg'
                        # save avatar to disk if requested, and if it does not already exist
                        if USE_LOCAL_THUMBNAIL and not avatar_local in output_lists.avatars_list: 
                            #time.sleep(random.randint(5, 10) / 10)  
                            avatar_local = Save_avatar(avatar_href, output_lists.avatars_dir)
        
            # if logged-in, we can determine if this user has been followed or not
            if user_inputs.password != '':
                try:          
                    class_name_ele = check_and_get_ele_by_xpath(actor_info, '../..')  
                    if class_name_ele is not None:
                        class_name = class_name_ele.get_attribute('class')
                        following_status = 'Following' if class_name.find('following') != -1  else 'Not Follow'
                except NoSuchElementException:
                    following_status = 'Unknown'
                    pass

            # get followers count
            number_of_followers = ''
            texts = actor_info.text.split('\n')
            if len(texts) > 1: 
                display_name = texts[0] 
                count = texts[1]
                number_of_followers =  count.replace(' followers', '').replace(' follower', '') 

        except:  # log any errors during the process but do not stop 
            printR(f'\nError on getting user # {i + 1}: name: {display_name}, user name: {user_name}.Some info may be missing!')

        followers_list.append(user(order = str(i+1), avatar_href = avatar_href, avatar_local = avatar_local, display_name= display_name, 
                                   user_name = user_name, id = user_id, number_of_followers = number_of_followers, following_status = following_status))
    return followers_list 

#---------------------------------------------------------------
def Does_this_user_follow_me(driver, user_inputs):
    """Check if a target_user follows a given user

    PROCESS:
    Get the list of users that the target user is following, then check if the list containt the given user name
    for better performance, we do not load the full list but rather one scroll-down at a time. We will scrolling down for more only if needed:
    - open the targer user home page, locate the text following and click on it to open the modal windonw containing following users list
    - scroll to the last loaded item to make all data available
    - make sure the document js is running for all the data to load in the page body
    - compare the user name of each load item to the given my_user_name. stop if a match is found, or continue to the next item until all the loaded items...
      are processed. scrolling down to load more items and repeat the process.
    """
    if driver.current_url != 'https://500px.com/' + user_inputs.target_user_name: 
        success, message = Open_user_home_page(driver, user_inputs.target_user_name)
        if not success:
            if message.find('Error reading') != -1:
                user_inputs.target_user_name = ''
            return False, message
  
    Hide_banners(driver)     
    ele = check_and_get_ele_by_xpath(driver, '//*[@id="content"]/div[1]/div[4]/ul/li[4]')   
    
    # extract number of following                       
    following_count_ele = check_and_get_ele_by_tag_name(ele, 'span')    
    if following_count_ele is None or following_count_ele.text == '0':
        return  False, "Status unknown. Timed out on getting the Following Count"
    else:
        following_count = int(following_count_ele.text.replace(",", "").replace(".", ""))
        print(f'    - User {user_inputs.target_user_name} is following {str(following_count)} user(s)')
  
    # click on the Following text to open the modal window
    if ele is not None:

       driver.execute_script("arguments[0].click();", ele)

    # abort the action if the target objects failed to load within a given timeout
    if not Finish_Javascript_rendered_body_content(driver, time_out=30, class_name_to_check='actors')[0]:
        return  False, "Status unknown. Timed out on loading more users"

    # start the progress bar
    update_progress(0, '    - Processing loaded data:')
    iteration_num = math.floor(following_count / LOADED_ITEM_PER_PAGE) + 1    

    users_done = 0
    current_index = 0   # the index of the photo in the loaded photos list. We dynamically scroll down the page to load more photos as we go, so ...
                        # ... more photos are appended at the end of the list. We use this current_index to keep track where we were after a list update 
    
 
    actor_infos = driver.find_elements_by_class_name('actor_info')
    loaded_users_count = len(actor_infos)
    while users_done < following_count: 
        # check if we have processed all loaded users, then we have to load more  
        if current_index >= loaded_users_count: 
            prev_loaded_users = loaded_users_count
            # loading more users by scrolling into view the last loaded item
            last_item_on_page =  current_index -1  #i * LOADED_ITEM_PER_PAGE - 1
            try:
                last_loaded_item = check_and_get_ele_by_xpath(driver, '//*[@id="modal_content"]/div/div/div/div/div[2]/ul/li[' + str(last_item_on_page) + ']')                                                                   
                if last_loaded_item is not None:
                    last_loaded_item.location_once_scrolled_into_view
                    time.sleep(1)
            except NoSuchElementException:
                pass

            # abort the action if the target objects failed to load within a given timeout 
            if not Finish_Javascript_rendered_body_content(driver, time_out=30, class_name_to_check='finished')[0]:
               return  False, "Status unknown. Timed out loading more user"
            time.sleep(1)

            # update list with more users
            actor_infos = driver.find_elements_by_class_name('actor_info')
            #time.sleep(1)
            loaded_users_count = len(actor_infos)
 
            # stop when all photos are loaded
            if loaded_users_count == prev_loaded_users:
                if loaded_users_count < following_count:
                    return False, f'Status unknown. Timed out {loaded_users_count}/{following_count}'
                break;

        following_user_name = ''
        following_user_page_link = ''
        for i in range(current_index, min(loaded_users_count, following_count)):
            if current_index > loaded_users_count: 
                break
            current_index += 1
            actor = actor_infos[i]
            update_progress(current_index / following_count, f'    - Processing loaded data {current_index}/{following_count}:')  
            try:
                ele = check_and_get_ele_by_class_name(actor, 'name')  
                if ele is not None:
                    following_user_page_link = ele.get_attribute('href')
                    following_user_name = following_user_page_link.replace('https://500px.com/', '')

                    if following_user_name is not None and following_user_name == user_inputs.user_name:
                        update_progress(1, f'    - Processing loaded data {current_index}/{following_count}:')
                        return True, f'Following you ({current_index}/{following_count})'

            except NoSuchElementException:
                continue  #ignore if follower name not found
        users_done = current_index
    return False, "Not following"

#---------------------------------------------------------------
# This is a time-consuming process for users that have thousands of following user. This option is taken off from the main menu. 
# I'm evaluating the multiprocessing approach, on processing the already loaded data, not on multiple requests to the server.Stay tuned. For now I have a limit on the request number.
def Get_following_statuses(driver, user_inputs, output_lists, csv_file):
    """ Get the following statuses of the users that you are following, with the option to specify the range of user in the following list.
   
    - start_user_index is 1-based and will be converted to 0-based
    - number_of_users : this is a lengthy process, so we provide this option to limit the number of users we will process. passing -1 to ignore this limit
    """

    # do main task
    df = pd.read_csv(csv_file, encoding='utf-16') #, usecols=["User Name"])     
    # a trick to force column Status content as string instead of the default float      
    df.Status = df.Status.fillna(value="")             
    # make sure the user's inputs stay in range with the size of the following list
    user_inputs.index_of_start_user = min(user_inputs.index_of_start_user, df.shape[0] -1)
    print('    Updating the following statuses on')
    printY(f'    {csv_file}')
    print(f'    ({user_inputs.number_of_users} users, starting from {user_inputs.index_of_start_user + 1}) ...')
   
    # process each user in dataframe
    count = 0

    # if requesting all items:
    if user_inputs.index_of_start_user == -1:
        start_index = 0
        end_index = df.shape[0] -1
    else:
        # make sure the user's inputs stay within the size of the csv file 
        start_index = min(user_inputs.index_of_start_user, df.shape[0] -1)
        end_index   = min(user_inputs.index_of_start_user + user_inputs.number_of_users, df.shape[0] -1)

    for index, row in df.iloc[start_index:end_index].iterrows():
        if index < user_inputs.index_of_start_user:
            continue
        if user_inputs.number_of_users != -1 and index > user_inputs.index_of_start_user + user_inputs.number_of_users - 1:
            break
        user_inputs.target_user_name = row["User Name"]
        count += 1
        print(f'    User {count}/{user_inputs.number_of_users} (index {index + 1}):')
        result, message = Does_this_user_follow_me(driver, user_inputs)
        if result == True:
            printG('- ' + message)
            # update the status column in the dataframe with following status
            df.at[index, 'Status'] = message 
        else:
            printR('- ' + message) if 'User name not found' in message else printY('- ' + message)
            continue
    try:
        # write back dataframe to csv file
        df.to_csv(csv_file, encoding='utf-16', index = False)
        #return csv_file
    except: # pd.Errors.csv_file:
        printR(f'Error writing file {os.path.abspath(csv_file)}.\nMake sure the file is not in use. Then type r for retry >')
        retry = input()
        if retry == 'r': 
            df.to_csv(csv_file, encoding='utf-16', index = False)
            #return csv_file
        else:
            printR('Error writing file' + os.path.abspath(csv_file))
            #return ''


#---------------------------------------------------------------
def Get_followings_list(driver, user_inputs, output_lists):
    """Get the list of users who I'm  following. Info for each item in the list are: 
       No, Avatar Href, Avatar Local, Display Name, User Name, ID, Followers, Status

    PROCESS:
    - Open the user home page, locate the text "followings" and click on it to open the modal windonw that hosts followers list
    - Scroll to the end for all items to be loaded
    - Make sure the document js is completed for all the data to load in the page body
    - Extract info and put in a list. 
    - Return the list
    """

    followings_list = []
    if driver.current_url != 'https://500px.com/' + user_inputs.user_name:
        success, message = Open_user_home_page(driver, user_inputs.user_name)
        if not success:
            printR(message)
            if message.find('Error reading') != -1:
                user_inputs.user_name = ''
            return followings_list

    Hide_banners(driver)                  
                                          
    # click on the Following text to open the modal window
    ele = check_and_get_ele_by_xpath(driver, '//*[@id="content"]/div[1]/div[4]/ul/li[4]')     
    try:
        if ele is None:
            printR('Error on getting the followings list')
            return followings_list
        else:
            ele.click()
    except:
        # you may get an exception here because of the tooltip on the element
        #printR("   Error on opening the Following list. Please try again.")
        pass

    # abort the action if the target objects failed to load within a given timeout    
    if not Finish_Javascript_rendered_body_content(driver, time_out=15, class_name_to_check='actors')[0]:
        return followings_list
            
    # extract number of following                      
    following_ele = check_and_get_ele_by_xpath(driver, '//*[@id="modal_content"]/div/div/div/div/div[1]/span') 
    if following_ele is None:
        return followings_list

    # remove thousand separator character, if existed
    following_count = int(following_ele.text.replace(",", "").replace(".", ""))
    print(f'    User {user_inputs.user_name} is following { str(following_count)} user(s)')
    

    # keep scrolling the modal window, 50 followers at a time, until the end, where the followings count is reached 
    iteration_num = math.floor(following_count / LOADED_ITEM_PER_PAGE) + 1 
    for i in range(1, iteration_num):
        update_progress(i / (iteration_num -1 ), f'    - Scrolling down to load all following users {i}/{iteration_num -1}')
        last_item_on_page = i * LOADED_ITEM_PER_PAGE - 1
        try:
            the_last_in_list = driver.find_elements_by_xpath('//*[@id="modal_content"]/div/div/div/div/div[2]/ul/li[' + str(last_item_on_page) + ']')[-1]                                                             
            the_last_in_list.location_once_scrolled_into_view
            time.sleep(1)
        except NoSuchElementException:
            printR('    Error while scrolling down to load more item')
            pass

    #Scroll_to_end_by_class_name(driver, 'actor_info', following_count)
 
    # now that we have all followers loaded, start extracting info
    update_progress(0,f'    - Extracting data 0/{following_count}:')
    actor_infos = driver.find_elements_by_class_name('actor_info')
    lenght = len(actor_infos)

    
    for i, actor_info in enumerate(actor_infos):
        if i > 0:
            update_progress( i / (len(actor_infos) - 1), f'    - Extracting data {i + 1}/{following_count}:')

        user_name, display_name, followings_page_link, count, number_of_followers = '', '', '','', ''  
        avatar_href, avatar_local, user_id = '', ' ', '0'
        try:
            # get user name 
            ele = check_and_get_ele_by_class_name(actor_info, 'name')
            #time.sleep(random.randint(5, 10) / 10)   
            if ele is not None:
                following_page_link = ele.get_attribute('href')
                user_name = following_page_link.replace('https://500px.com/', '')

            # get user avatar and user id
            actor_info_parent_ele = check_and_get_ele_by_xpath(actor_info, '..')   
            if actor_info_parent_ele is not None:
                avatar_ele = check_and_get_ele_by_class_name(actor_info_parent_ele, 'avatar')
                if avatar_ele is not None:
                    style = avatar_ele.get_attribute('style')
                    avatar_href =  style[style.find('https'): style.find('\")')]

                    if 'userpic.png' in avatar_href:
                        if USE_LOCAL_THUMBNAIL:
                            avatar_local = 'userpic.png'
                    else:
                        user_id  =  re.search('\/user_avatar\/(\d+)\/', avatar_href).group(1)
                        avatar_local = user_id + '.jpg'
                        # save avatar to disk if requested, and if it does not already exist
                        if USE_LOCAL_THUMBNAIL and not avatar_local in output_lists.avatars_list: 
                            #time.sleep(random.randint(5, 10) / 10)  
                            avatar_local = Save_avatar(avatar_href, output_lists.avatars_dir)


            # get followers count
            texts = actor_info.text.split('\n')
            if len(texts) > 0: display_name = texts[0] 
            if len(texts) > 1: count = texts[1]; 
            number_of_followers =  count.replace(' followers', '').replace(' follower', '')  


        except:  # log any errors during the process but do not stop 
            printR(f'\nError on getting user # {i + 1}: name: {display_name}, user name: {user_name}.Some info may be missing!')

        # create user object and add it to the result list 
        followings_list.append(user(order = str(i+1), avatar_href = avatar_href, avatar_local = avatar_local, display_name = display_name, 
                                    user_name = user_name, id = user_id, number_of_followers = number_of_followers))
    return followings_list

#---------------------------------------------------------------

def Process_notification_element(notification_element, output_lists):
    """Process one notification item. Return a notification object of the following detail:
    No, Avatar Href, Avatar Local, Display Name, User Name, ID, Content, Photo Thumbnail Href, Photo Thumbnail Local, Photo Title, Time Stamp, Status, Photo Link

    """

    display_name, user_name, content, photo_title, photo_link, status, timestamp = '', '', '', '', '', '', '' 
    avatar_href, avatar_local, user_id =  '', ' ', '0',
    photo_thumbnail_href, photo_thumbnail_local, photo_id = '', '',  '0'
    try:
        # get user_name, display_name
        actor = check_and_get_ele_by_class_name(notification_element, 'notification_item__actor') 
        if actor is None:
            return None
        display_name = actor.text

        user_name = actor.get_attribute('href').replace('https://500px.com/', '')

        # ignore Quest notification
        if 'quests/' in user_name:
            return None

        # get user avatar, user id   
        avatar_ele = check_and_get_ele_by_class_name(notification_element, 'notification_item__avatar_img')             
        #time.sleep(random.randint(5, 10) / 10)  

        if avatar_ele is None:
            return None
        avatar_href = avatar_ele.get_attribute('src')

        # user has default avatar
        if 'userpic.png' in avatar_href:
            if USE_LOCAL_THUMBNAIL:
                avatar_local = 'userpic.png'
        else:
            user_id  =  re.search('\/user_avatar\/(\d+)\/', avatar_href).group(1)
            avatar_local = user_id + '.jpg'
            # save avatar to disk if requested, and if it does not already exist
            if USE_LOCAL_THUMBNAIL and not avatar_local in output_lists.avatars_list: 
                #time.sleep(random.randint(5, 10) / 10)  
                avatar_local = Save_avatar(avatar_href, output_lists.avatars_dir)

        # the type of notificication
        item_text = check_and_get_ele_by_class_name(notification_element, 'notification_item__text')  
        if item_text is not  None:
            if item_text.text.find('liked') != -1: 
                content = 'liked'
            elif item_text.text.find('followed') != -1: 
                content = 'followed'
            elif item_text.text.find('added') != -1: 
                content = 'added to gallery'
            elif item_text.text.find('commented') != -1: 
                content = 'commented'
            else: 
                content = item_text.text

        # photo title, photo link
        photo_ele = check_and_get_ele_by_class_name(item_text, 'notification_item__photo_link')
 
        # in case of a new follow, instead of a photo element, there will be 2 overlapping boxes, Follow and Following. We will determine if whether or not this actor has been followered  
        if photo_ele is None:  
            following_box = check_and_get_ele_by_class_name(notification_element, 'following')
            if following_box is not None and following_box.is_displayed():        
                status = 'Following'
            else:  
                status = 'Not Follow'  
        else: 
            photo_title = photo_ele.text
            photo_link = photo_ele.get_attribute('href') 

        # get photo thumbnail
        photo_thumb_ele = check_and_get_ele_by_class_name(notification_element, 'notification_item__photo_img') 
        #time.sleep(random.randint(5, 10) / 10)
        if photo_thumb_ele is not None:
            photo_thumbnail_href = photo_thumb_ele.get_attribute('src')
            # save the photo thumbnail to disk
            if USE_LOCAL_THUMBNAIL:
                photo_thumbnail_local = Save_photo_thumbnail(photo_thumbnail_href, output_lists.thumbnails_dir )
                if photo_thumbnail_local:
                    photo_id = os.path.splitext(photo_thumbnail_local)[0]
        
        # time stamp
        ele = check_and_get_ele_by_class_name(notification_element, 'notification_item__timestamp')  
        timestamp  = ele.text if ele is not None else ""

    except:  # log any errors during the process but do not stop 
        printR(f'\nError on getting notification: actor: {display_name}, photo_title: {photo_title}\nSome info may be missing!')

    # creating and return the notification object
    the_actor = user(avatar_href = avatar_href, avatar_local = avatar_local, display_name = display_name, user_name = user_name, id = user_id)
    the_photo = photo(thumbnail_href = photo_thumbnail_href, thumbnail_local = photo_thumbnail_local, id = photo_id, href = photo_link, title = photo_title)

    return notification(order = 0, actor = the_actor, the_photo = the_photo, content = content, timestamp = timestamp,  status = status)
   
#---------------------------------------------------------------
def Process_notifications(request_number, items, output_lists):
    """Given a list of notification web elements and a number of requested notifications, extract info and return a list of notification objects """

    notifications =[]
    for i, item in enumerate(items):
        count_sofar = len(notifications)    
        if count_sofar >= request_number:
            break
        
        new_notification = Process_notification_element(item, output_lists)
        if new_notification is not None:
            count_sofar += 1
            new_notification.order = count_sofar
            notifications.append(new_notification)
            # advance the progress bar
            update_progress(count_sofar/request_number, f'    - Extracted data {count_sofar}/{request_number}:') 
    return notifications

#---------------------------------------------------------------
def Get_notification_list(driver, user_inputs, output_lists, get_full_detail = True ):
    """Get n last notification items. Return 2 lists, notifications list and a list of unique users from it, along with the count of appearances of each user
    
    A detailed notification item contains full_name, user name, the content of the notification, title of the photo in question, the time stamp and a status
    A short notification item contains just full name and user name
    A unique notification list is a short notification list where all the duplication are removed.
    If the given GET_FULL_DETAIL is true, return the detailed list, if false, return the unique list
    PROCESS:
    - expecting the user was logged in, and the notification page is the active page
    - scroll down until all the required number of notifications are loaded
    - extract info.
    - Return two lists, the notifications list, and a simplified list, containing the unique users on the first list. 
    """

    unique_notificators, notifications_list, simplified_list = [],[], []

    Scroll_down_active_page(driver, None, 'notification_item__photo_link', '', user_inputs.number_of_notifications, '    - Scrolling down for more notifications:' ) 

    # get the info now that all we got all the available notifications
    items = driver.find_elements_by_class_name('notification_item')  

    notifications_list = Process_notifications(user_inputs.number_of_notifications, items, output_lists)
    
    if len(notifications_list) == 0 and len(unique_notificators) == 0: 
        printG(f'User {user_inputs.user_name} has no notification')
        return [], []

    # create the simplified list from the notifications list for easy manipulation
    # each item in the list is a comma-separated string of avatar link, display name and user name
    simplified_list = [f'{item.actor.avatar_href},{item.actor.avatar_local},{item.actor.display_name.replace(",", " ")},{item.actor.user_name},{item.actor.id} ' for item in notifications_list]
    
    # extract the unique users and the number of times they appear in the notifications list  
    unique_notificators = Count_And_Remove_Duplications(simplified_list)

    # add order number at the beginning of each row
    for j in range(len(unique_notificators)):
        unique_notificators[j] = f'{str(j+1)},{unique_notificators[j]}'

    return notifications_list, unique_notificators


#---------------------------------------------------------------
def Get_like_actioners_list(driver, output_lists):
    """Get the list of users who liked a given photo. Return the list a suggested file name that includes owner name, photo title and the like count

    PROCESS:
    - Expecting the active page in the browser is the given photo page
    - Run the document js to render the page body
    - Extract photo title and photographer name
    - Locate the like count number then click on it to open the modal window hosting the list of actioner user
    - Scroll down to the end and extract relevant info, put all to the list and return it
    """
    time_out = 20
    actioners_list = []
    date_string = datetime.datetime.now().replace(microsecond=0).strftime(DATE_FORMAT)

    try:  
        info_box = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.XPATH, '//*[@id="root"]/div[3]/div/div[2]')) )
    except  TimeoutException:
        printR(f'    Time out ({time_out}s)! Please try again')
        return [], ''
  
    print('     - Getting photo details ...')
    # get photographer name
    photographer_ele = check_and_get_ele_by_xpath(info_box, '//div[2]/div[1]/p[1]/span/a')
    if photographer_ele is None: 
        photographer_name = ''
        printR('   Error getting photographer name')
    else:
        photographer_name = photographer_ele.text
        printG(f'   Photogapher: {photographer_name}')

    # get photo title
    title_ele = check_and_get_ele_by_xpath(info_box, '//div[2]/div[1]/h3')
    if title_ele is None: 
        photo_title = ''
        printR('Error getting photo title')
    else:
        photo_title = title_ele.text
        printG(f'   Photo title: {photo_title}')

    # Get the like-count-button and click on it to open the modal window that host the actioners list
    try:
        photo_likes_count_ele = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.XPATH, '//a[@data-id="photo-likes-count"]')) )
    except  TimeoutException:
        printR(f'Time out ({time_out}s! Please try again')
        return [], ''

    likes_count_string = photo_likes_count_ele.text
    likes_count = int(likes_count_string.replace('.','').replace(',',''))
    printG(f"   This photo has {likes_count} likes")

    photo_likes_count_ele.click()
    
    try:
        WebDriverWait(driver, time_out).until( EC.presence_of_element_located((By.CLASS_NAME, 'ant-modal-body')) )
    except  TimeoutException:
        printR(f'Time out ({time_out}s! Not all elements are loaded. You may try again later.')
 
    # make a meaningful output file name
    like_actioners_file_name = os.path.join(output_lists.output_dir, \
        f"{photographer_name.replace(' ', '-')}_{likes_count}_likes_{photo_title.replace(' ', '-')}_{date_string}.csv")

    #get a container element containing all actors
    container= check_and_get_ele_by_class_name(driver,'ant-modal-body')
    time.sleep(1)
    if container is None:
        return [], ''
    #scrolling down until all the actors are loaded
    img_eles = Scroll_to_end_by_tag_name_within_element(driver, container, 'img', likes_count)
    #Scroll_down_active_page(driver, container, '', 'img', likes_count, ' - Scrolling down for more items:' ) 
   
    # create actors list
    actors_count = len(img_eles )
    for i, img in enumerate(img_eles):
        update_progress(i / (actors_count - 1), f'    - Extracting data {i+1}/{actors_count}:')

        display_name, user_name, followers_count, following_status = '', '', '', ''
        avatar_href, avatar_local, user_id = '', ' ', '0'

        try: 
            display_name = img.get_attribute('alt')
            # get user avatar source, user id, and save avatar thumbnail to disk
            avatar_href= img.get_attribute('src')      
            # if user has default avatar
            if 'userpic.png' in avatar_href:
                if USE_LOCAL_THUMBNAIL:
                    avatar_local = 'userpic.png'
            else:
                user_id  =  re.search('\/user_avatar\/(\d+)\/', avatar_href).group(1)
                avatar_local = user_id + '.jpg'
                # save avatar to disk if requested, and only if it does not exist
                # this means that if the users changed theirs avatars we won't see the change. 
                # To get the latest version of an avatar, we have to identify the file on the list and delete it before running the script
                if USE_LOCAL_THUMBNAIL and not avatar_local in output_lists.avatars_list:
                    #time.sleep(random.randint(5, 10) / 10)  
                    avatar_local = Save_avatar(avatar_href, output_lists.avatars_dir)

            img_ele_parent =  check_and_get_ele_by_xpath(img, '..')
            if img_ele_parent is None:
                continue
            user_name = img_ele_parent.get_attribute('href').replace('https://500px.com/','')

            follower_count_text_ele =  check_and_get_ele_by_xpath(img_ele_parent, '..') 
            if follower_count_text_ele is None: 
                continue
            texts = follower_count_text_ele.text.split('\n')
            if len(texts) > 1:
                followers_count  = re.sub('[^\d]+', '', texts[1]) 
            
            # get following status
            following_status = 'Not follow'
            following_status_ele = check_and_get_ele_by_xpath(img, '../../../../div[2]/a/span')
            if following_status_ele is None:
                continue
            if 'Unfollow' in following_status_ele.get_attribute("innerHTML"):
                following_status = 'Following'

        except:  # log any errors during the process but do not stop 
            printR(f'\nError on getting user # {i + 1}: name: {display_name}, user name: {user_name}.Some info may be missing!')

        actioners_list.append(user(order = str(i+1), avatar_href = avatar_href, avatar_local = avatar_local, display_name = display_name, 
                                    user_name = user_name, id = user_id, number_of_followers = str(followers_count), following_status = following_status) )
        
    return actioners_list, like_actioners_file_name 
#---------------------------------------------------------------
def Like_n_photos_from_user(driver, target_user_name, number_of_photos_to_be_liked, include_already_liked_photo_in_count = True, close_browser_on_error = True):
    """Like n photo of a given user, starting from the top. Return False and error message if error occured, True and blank string otherwise

    If the include_already_liked_photo is true (default), the already-liked photo will be counted as done by the auto-like process
    for example, if you need to auto-like 3 photos from a user, but two photos in the first three photos are already liked, 
    then you only need to do one
    If the include_already_liked_photo_in_count is false, the process will auto-like the exact number requested
    the argument close_browser_on_error needs to be false if this function is called in a loop: if errors occur, we want to process the next item
    PROCESS:
    - Open the user home page
    - Force document js to run to fill the visible body
    - Locate the first photo, check if it is already-liked or not, if yes, go the next photo, it no, click on it to like the photo
    - Continue until the asking number of photos is reached. 
    - When we have processed all the loaded photos but the required number is not reached yet, 
      scroll down once to load more photos ( currently 500px loads 50 photos at a time) and repeat the steps until done
      """

    success, message = Open_user_home_page(driver, target_user_name)
    if not success:
        return False
    
    # pause a random time between 0.5s, 1s for human-like effect
    #time.sleep(random.randint(5, 10) / 10)   
    # abort the action if the target objects failed to load within a given timeout    
    if not Finish_Javascript_rendered_body_content(driver, time_out=60, class_name_to_check='finished')[0]:
        return False, 

    Hide_banners(driver)        
    
    new_fav_icons =  check_and_get_all_elements_by_css_selector(driver, '.button.new_fav.only_icon') 
    time.sleep(random.randint(5, 10) / 10)   
    if len(new_fav_icons) == 0:
        printY('   User has no photos')
    done_count = 0

    for i, icon in enumerate(new_fav_icons):
        icon.location_once_scrolled_into_view
        # skip already-liked photo. Count it as done if requested so
        if done_count < number_of_photos_to_be_liked and 'heart' in icon.get_attribute('class'): 
            if include_already_liked_photo_in_count == True:
                done_count = done_count + 1          
            printY(f'   - liked #{str(done_count):3} Photo { str(i+1):2} - already liked')

            continue        

        # check limit
        if done_count >= number_of_photos_to_be_liked:  
            break
        
        Hover_by_element(driver, icon) # not necessary, but good for visual demonstration
        #time.sleep(random.randint(5, 10) / 10)
        try:
            title =  icon.find_element_by_xpath('../../../../..').find_element_by_class_name('photo_link').find_element_by_tag_name('img').get_attribute('alt')
            if title and title == 'Photo':
                title = 'Untitled'
            driver.execute_script("arguments[0].click();", icon) 
            done_count = done_count + 1
            printG(f'   - liked #{str(done_count):3} Photo {str(i + 1):2} - {title:.50}')
            # pause a randomized time between 0.5 to 2 seconds between actions 
            #time.sleep(random.randint(5, 20) / 10)

        except Exception as e:
            printR(f'Error after {str(done_count)}, at index {str(i)}, title {title}:\nException: {e}')
            return False
    return True

#---------------------------------------------------------------
def Like_n_photos_on_current_page(driver, number_of_photos_to_be_liked, index_of_start_photo):
    """Like n photos on the active photo page. It could be either popular, popular-undiscovered, upcoming, fresh or editor's choice page."""

    title = ''
    photographer = ''
    photos_done = 0
    current_index = 0   # the index of the photo in the loaded photos list. We dynamically scroll down the page to load more photos as we go, so ...
                        # ... more photos are appended at the end of the list. We use this current_index to keep track where we were after a list update 
            
    # debug info: without scrolling, it would load (PHOTOS_PER_PAGE = 50) photos
    new_fav_icons = check_and_get_all_elements_by_css_selector(driver, '.button.new_fav.only_icon')  #driver.find_elements_by_css_selector('.button.new_fav.only_icon')
    loaded_photos_count = len(new_fav_icons)

    #optimization: at the begining, scrolling down to the desired index instead of repeatedly scrolling & checking 
    if index_of_start_photo > PHOTOS_PER_PAGE:
        estimate_scrolls_needed =  math.floor( index_of_start_photo / PHOTOS_PER_PAGE) +1
        Scroll_down(driver, 1, estimate_scrolls_needed, estimate_scrolls_needed, f' - Scrolling down to photos #{index_of_start_photo}:') 
        
        # instead of a fixed waiting time, we wait until the desired photo to be loaded  
        while loaded_photos_count < index_of_start_photo:
            new_fav_icons = check_and_get_all_elements_by_css_selector(driver, '.button.new_fav.only_icon')
            loaded_photos_count = len(new_fav_icons)
          
    while photos_done < number_of_photos_to_be_liked: 
        # if all loaded photos have been processed, scroll down 1 time to load more
        if current_index >= loaded_photos_count: 
            prev_loaded_photos = loaded_photos_count
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            # instead of a fixed waiting time, we wait until the desired photo to be loaded, within a given timeout  
            time_out = 15
            while loaded_photos_count <= current_index and time_out > 0:
                time_out -= 1
                new_fav_icons =  check_and_get_all_elements_by_css_selector(driver, '.button.new_fav.only_icon')  
                time.sleep(1)
                loaded_photos_count = len(new_fav_icons)

            # stop when all photos are loaded
            if loaded_photos_count == prev_loaded_photos:
                break;

        for i in range(current_index, loaded_photos_count):
            current_index += 1
            icon = new_fav_icons[i]

            # stop when limit reaches
            if photos_done >= number_of_photos_to_be_liked: break     
            # skip un-interested items  
            if i < index_of_start_photo - 1 : continue                   
            # skip already liked photo: 'liked' class is a subclass of 'new_fav_only_icon', so these elements are also included in the list
            if 'heart' in icon.get_attribute('class'): continue
            
            Hover_by_element(driver, icon) # not needed, but good to have a visual demonstration
            try:
                #intentional slowing down a bit to make it look more like human
                time.sleep(random.randint(5,10)/10)  

                photo_link = icon.find_element_by_xpath('../../../../..').find_element_by_class_name('photo_link')
                title =  photo_link.find_element_by_tag_name('img').get_attribute('alt')
                photographer_ele = check_and_get_ele_by_class_name(photo_link, 'photographer')

                if photographer_ele is not None:
                    photographer_ele.location_once_scrolled_into_view
                    Hover_by_element(driver, photographer_ele)
                    photographer = photographer_ele.text
                    photographer_ele.location_once_scrolled_into_view
                    Hover_by_element(driver, photographer_ele)
                    photographer = photographer_ele.text
                else:
                # if the current photos page is a user's gallery, there would be no photographer class.
                # We will extract the photographer name from the photo href, replacing any hex number in it with character, for now '*'
                    href =  photo_link.get_attribute('href')
                    subStrings = href.split('-by-')
                    if len(subStrings) > 1:
                        photographer =  re.sub('%\w\w', '*', subStrings[1].replace('-',' '))

                driver.execute_script("arguments[0].click();", icon) 
                photos_done = photos_done + 1

                printG(f'Liked {str(photos_done):>3}/{number_of_photos_to_be_liked:<3}, {photographer:<28.24}, Photo {str(i+1):<4} title {title:<35.35}')
            except Exception as e:
                printR(f'Error after {str(photos_done)}, at index {str(i+1)}, title {title}:\nException: {e}')
                printY('The page structure of this photo gallery is not recognizable. The process will stop.')
                # we set this to end the outer loop, while:
                photos_done = number_of_photos_to_be_liked
                break

#---------------------------------------------------------------
def Play_slideshow(driver, time_interval):
    """Play slideshow of photos on the active photo page in browser.

    PROCESS:
    Expecting the active page in browser is the photos page
    - Open the first photo by click on it
    - Click on the expand arrow to maximize the display area 
    - After a given time interval, locate the next button and click on it to show the next photo
    - Exit when last photo is reached
    """
    photo_links_eles = check_and_get_all_elements_by_class_name(driver, 'photo_link')
    loaded_photos_count = len(photo_links_eles)
 
    if len(photo_links_eles) > 0:
        # show the first photo
        driver.execute_script("arguments[0].click();", photo_links_eles[0])
        time.sleep(1)
					    
        # abort the action if the target objects failed to load within a given timeout    
        if not Finish_Javascript_rendered_body_content(driver, time_out=15, class_name_to_check = 'entry-visible')[0]:
            return None, None	
        
        # suppress the sign-in popup that may appear if not login
        Hide_banners(driver)
        
        # locate the expand icon and click it to expand the photo
        expand_icon = check_and_get_ele_by_xpath(driver, '//*[@id="copyrightTooltipContainer"]/div/div[2]') 
        if expand_icon is not None:
            driver.execute_script("arguments[0].click();",expand_icon)
        time.sleep(time_interval)
        
        # locate the next icon and click it to show the next image, after a time interval
        next_icon = check_and_get_ele_by_xpath(driver, '//*[@id="copyrightTooltipContainer"]/div/div[1]/div') 
        while next_icon is not None:
            driver.execute_script("arguments[0].click();", next_icon)
            time.sleep(time_interval)
            next_icon = check_and_get_ele_by_xpath(driver,  '//*[@id="copyrightTooltipContainer"]/div/div[2]/div/div[2]')  

#---------------------------------------------------------------                           
def Like_n_photos_on_homefeed_page(driver, user_inputs):
    """Like n photos from the user's home feed page, excluding recommended photos and skipping consecutive photo(s) of the same user
   
    PROCESS:
    - Expecting the user home feed page is the active page in the browser
    - Get the list elements representing loaded interested photos (the ones from photographers that you are following)
    - For each element in the list, traverse up, down the xml tree for photo title, owner name, like status, and make a decision to click the like icon or not
    - Continue until the required number is reached. along the way, stop and scroll down to load more photos when needed 
    """
    photos_done = 0
    current_index = 0  # the index of the photo in the loaded photos list. We dynamically scroll down the page to load more photos as we go, so ...
                       # ... we use this index to keep track where we are after a list update 
    prev_photographer_name = ''
    print(f"    Getting the loaded photos from {user_inputs.user_name}'s home feed page ...")
    img_eles = Get_IMG_element_from_homefeed_page(driver)
    loaded_photos_count = len(img_eles)
   
    while photos_done < user_inputs.number_of_photos_to_be_liked: 
        # check whether we have processed all loaded photos, if yes, scroll down 1 time to load more
        if current_index >= loaded_photos_count: 
            prev_loaded_photos = loaded_photos_count
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")                
            time.sleep(2)

            img_eles = Get_IMG_element_from_homefeed_page(driver)
            loaded_photos_count = len(img_eles)

            # stop when all photos are loaded
            if loaded_photos_count == prev_loaded_photos:
                break;

        for i in range(current_index, loaded_photos_count):
            # stop when done
            if photos_done >= user_inputs.number_of_photos_to_be_liked: 
                break
            current_index += 1
            photographer_name = ' '
            title = ' '
            parent2 = check_and_get_ele_by_xpath(img_eles[i], '../..')   
            if parent2 is None: 
                continue
                
            parent2_sib1 =  check_and_get_ele_by_xpath(parent2, './following-sibling::div') 
            if parent2_sib1 is None: 
                continue

            parent2_sib2 =  check_and_get_ele_by_xpath(parent2_sib1, './following-sibling::div') 
            if parent2_sib2 is  None: 
                continue    
            # for logging message, get photo title, photogragpher display name and  user name
            title_ele = check_and_get_ele_by_tag_name(parent2_sib2, 'h3') #title  = parent2_sib2.find_element_by_tag_name('h3').text            
            title = title_ele.text if title_ele is not None else 'not determined'
           
            a_ele = check_and_get_ele_by_tag_name(parent2_sib2, 'a')  #a = parent2_sib2.find_element_by_tag_name('a')
            photographer_display_name  = a_ele.text if a_ele is not None else "not determined"
            photographer_name = a_ele.get_attribute('href').replace('https://500px.com/', '') if a_ele is not None else "not determined"

            child_div_eles = check_and_get_all_elements_by_tag_name(parent2_sib1, 'div')
            if len(child_div_eles) > 2:
                heart_icon = child_div_eles[2]
                #get like status
                photo_already_liked = False
                svg_ele = check_and_get_ele_by_tag_name(heart_icon, 'svg')
                if svg_ele is not None:
                    title_ele = check_and_get_ele_by_tag_name(svg_ele, 'title')
                    if title_ele is not None:     
                        like_status = title_ele.get_attribute('innerHTML')
                        # skip if the photo is one of yours
                        if like_status.find('disabled') != -1:
                            printB(f'Skipped:      photo {str(i + 1):3}, from {photographer_display_name:<32.30}, {title:<35.35}')
                            continue                           
                        elif like_status.find('Filled') != -1:  # already liked: 'Filled', not-yet like: 'Outline', your own photo: 'disabled'
                            photo_already_liked = True
                        if  not photo_already_liked:      
                            # skip consecutive photos of the same photographer
                            if photographer_name == prev_photographer_name:
                                printY(f'Skipped:      photo {str(i + 1):3}, from {photographer_display_name:<32.30}, {title:<35.35}')
                                continue
                            if heart_icon is not None:
                                Hover_by_element(driver, heart_icon)
                                driver.execute_script("arguments[0].click();", heart_icon) 
                                photos_done += 1
                                prev_photographer_name = photographer_name
                                printG(f'Like {photos_done:>3}/{user_inputs.number_of_photos_to_be_liked:<3}: photo {str(i + 1):<3}, from {photographer_display_name:<32.30}, {title:<40.40}')
                                time.sleep(random.randint(10, 20)/10)  # slow down a bit to make it look more like a human

#---------------------------------------------------------------
def Count_And_Remove_Duplications(values):
    """Given a list containing the comma-separated strings of avatar href, avatar local, display name, user name and id( such as "http://...,  C://LocalAvatar, John Doe, johndoe, 1234567" ).
       Count the duplication of each item in the list then remove the duplicated entry(ies). Append the count to each entry's count column.
       An output list item has this form: Avatar Href, Avatar Local, Display Name, User Name, ID, Count"""

    output = []
    seen = set()
    count = 0
    for value in values:
        # If value has not been encountered yet, add it to the seen set then append count as "1" to value and add it to ouput list.
        if value not in seen:           
            seen.add(value)
            output.append(value + ', 1')
        else:
            indexes = (output.index(s) for s in output if value in s)
            index = next(indexes)
            list_items = output[index].split(',')
            try:
                if len(list_items) == 6:
                    new_count = int(list_items[5]) + 1
               # elif len(list_items) == 4: # just in crazy situation where display name has comma in it 
               #     new_count = int(list_items[3]) + 1
                output[index] = f'{list_items[0]},{list_items[1]},{list_items[2]},{list_items[3]},{list_items[4]},{new_count}'
            except:
                continue
    return output    


#---------------------------------------------------------------
def Scroll_down_active_page(driver, web_element, class_name_to_check, tag_name_to_check, number_of_items_requested = 100, message = '', time_out= 60):
    """Scrolling down the active window until all the request items of a given class name or a tag name, are loaded.

    - The process monitors the change of the page height to decide if another scroll down is needed
      After a scroll down, if the server fails to load new items within a given time out (default is 60s), the process will stop 
    - If both class name and tag name are given, class name take priority. if none is given, no action is taken
    - Message is the text shown on the progress bar

"""
    if web_element is None:
        web_element = driver    
    if class_name_to_check: 
        items = web_element.find_elements_by_class_name(class_name_to_check) 
    elif tag_name_to_check: 
        items = web_element.find_elements_by_tag_name(tag_name_to_check) 
    else:
        printR('Items were not specified. The process stopped.')
        return
    if items is None or len(items) == 0:
        printR('No items found.')
        return
      
    if len(items) >= number_of_items_requested:
        return    
     
    # get the current height of the page
    last_scroll_height = driver.execute_script("return document.body.scrollHeight")

    time_out_count_down = time_out
    count_sofar = 0
    if number_of_items_requested == -1:
        number_of_items_requested  = MAX_NOTIFICATION_REQUEST

    while count_sofar < number_of_items_requested :   
        update_progress(count_sofar / number_of_items_requested, f'    - Scrolling down {count_sofar}/{number_of_items_requested}')
        # scroll down to bottom
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        new_scroll_height = driver.execute_script("return document.body.scrollHeight")

        # give the slow server a chance to load the new items
        while new_scroll_height == last_scroll_height and time_out_count_down >= 0:
            time_out_count_down -= 1
            new_scroll_height = driver.execute_script("return document.body.scrollHeight") 
            time.sleep(1)
 
        last_scroll_height = new_scroll_height

        if class_name_to_check : 
            items = web_element.find_elements_by_class_name(class_name_to_check)         
        elif tag_name_to_check: 
            items = web_element.find_elements_by_tag_name(tag_name_to_check) 

        count_sofar = len(items)    

        if count_sofar < number_of_items_requested and time_out_count_down <= 0:
            printR(f'\r Time out ({time_out}s)! {count_sofar}/{number_of_items_requested} items obtained. You may try again at another time')
            break
 
    # normal termination of while loop: show completed progress bar
    else:
        update_progress(1, f'    - Scrolling down {number_of_items_requested}/{number_of_items_requested}')


#---------------------------------------------------------------
def Scroll_down(driver, scroll_pause_time = 0.5, number_of_scrolls = 10, estimate_scrolls_needed = 3, message = ''):
    """Scrolling down the active window in a controllable fashion.

    Passing the scroll_pause_time according to the content of the page, to make sure all items are loaded before the next scroll. default is 0.5s
    The page could have a very long list, or almost infinity, so by default we limit it to 10 times.
    If number_of_scrolls =  0, return without scrolling
    If number_of_scrolls = -1, keep scrolling until the end is reached ...
    for this case, in order to have a realistic progress bar, we will use estimate_scrolls_needed  ( total request items / load items per scroll )
    Message is a string described the title of the progress bar. if empty is passed, the progress bar will not be stimulated
    """
    if number_of_scrolls == 0 :
        return

    # Get scroll height
    last_height = driver.execute_script("return document.body.scrollHeight")
    iteration_count = 0
    scrolls_count_for_stimulated_progressbar = 0
    while True:
        if number_of_scrolls == -1:
            # if we were able to give an estimate of number of scrolls needed (ex. number of photos, followers, friends are known)
            if estimate_scrolls_needed != -1: 
                update_progress(scrolls_count_for_stimulated_progressbar / estimate_scrolls_needed, message)
            # here, we dont know when it ends (for example, we ask for all notifications, but we don't know how many the 500px server will provide) 
            else:
                notifications_loaded_so_far = scrolls_count_for_stimulated_progressbar * NOTIFICATION_PER_LOAD
                text = f'\r{message} {str(notifications_loaded_so_far)}'
                sys.stdout.write(text)
                sys.stdout.flush()
        elif iteration_count > 0:
            update_progress(iteration_count / number_of_scrolls, message)

        scrolls_count_for_stimulated_progressbar += 1

        # Scroll down to bottom
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

        # Wait for page to load
        time.sleep(scroll_pause_time)
        innerHTML = driver.execute_script("return document.body.innerHTML") #make sure document javascript is executed

        # exit point #1 : when number of scrolls requested has been reached
        if number_of_scrolls != -1:
            iteration_count = iteration_count + 1
            if iteration_count >= number_of_scrolls:
               break

        #  exit point #2: when all items are loaded (by calculating new scroll height and compare with last scroll height)
        #                 or when the server stop responding after the given sleep time (scroll_pause_time)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    # mark the end of the progress bar update    
    if number_of_scrolls == -1 and estimate_scrolls_needed == -1:   # indeterminate number of scrolls
        sys.stdout.write('\r\n')                                    # end the progress update with a line-feed
        sys.stdout.flush()
    else:
        update_progress(1, message)                                 # force the display of "100% Done" 
  
    time.sleep(scroll_pause_time)
#---------------------------------------------------------------
def Scroll_to_end_by_class_name(driver, class_name, likes_count):
    """Scroll the active window to the end, where the last element of the given class name become visible.

    Argument LIKES_COUNT is used for creating a realistic progress bar
    """
    eles = driver.find_elements_by_class_name(class_name)
    count = 0
    new_count = len(eles)

    while new_count != count:
        try:
            update_progress(new_count / likes_count, f'    - Scrolling to load more items {new_count}/{likes_count}:')
            the_last_in_list = eles[-1]
            the_last_in_list.location_once_scrolled_into_view 
            time.sleep(random.randint(5, 10) / 10)  
            WebDriverWait(driver, timeout = 60).until(EC.visibility_of(the_last_in_list))
            count = new_count
            eles = driver.find_elements_by_class_name(class_name)
            new_count = len(eles)
        except TimeoutException :
            printR(f'    Time out while scrolling down. Please retry.')
        except NoSuchElementException:
            pass
    if new_count < likes_count:
        update_progress(1, f'    - Scrolling to load more items:{likes_count}/{likes_count}')

#---------------------------------------------------------------
def Scroll_to_end_by_tag_name_within_element(driver, element, tag_name, likes_count):
    """Scroll the active window to the end, where the last element of the given tag name is loaded and visible.

    Argument LIKES_COUNT is used for creating a realistic progress bar
    """
    eles = check_and_get_all_elements_by_tag_name(element, tag_name)
    count = 0
    new_count = len(eles)
    time_out = 20
    count_down_timer = time_out
    while new_count != count:
        try:
            update_progress(new_count / likes_count, f'    - Scrolling to load more items {new_count}/{likes_count}:')
            the_last_in_list = eles[-1]
            the_last_in_list.location_once_scrolled_into_view 
            time.sleep(1)
            WebDriverWait(driver, time_out).until(EC.visibility_of(the_last_in_list))
            count = new_count
            eles = check_and_get_all_elements_by_tag_name(element, tag_name)
            new_count = len(eles)

            # give the slow server a chance to load the new items 
            while new_count == count and count_down_timer >= 0 and new_count < likes_count:
                count_down_timer -= 1
                the_last_in_list.location_once_scrolled_into_view 
                time.sleep(1)

        except TimeoutException :
            printR(f'Time out ({time_out}s) while scrolling down. Please retry.')
        except NoSuchElementException:
            pass
    if new_count >= likes_count:
        update_progress(1, f'    - Scrolling to load more items:{likes_count}/{likes_count}')
    return eles

#---------------------------------------------------------------
def Login(driver, user_inputs):
    """Submit given credentials to the 500px login page. Display error message if error occured. Return True/False loggin status """

    if len(user_inputs.password) == 0 or len(user_inputs.user_name) == 0 or driver == None: 
        return False
    print(f'    Logging in user {user_inputs.user_name} ...')
    time_out = 60
    driver.get("https://500px.com/login" )
    try:
        user_name_ele = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.ID, 'emailOrUsername'))) # 'email')))
        user_name_ele.send_keys(user_inputs.user_name) 
        
        pwd_ele = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.ID, 'password')))
        pwd_ele.send_keys(user_inputs.password) 

        submit_ele =  check_and_get_ele_by_xpath(user_name_ele, '../following-sibling::button') 
        if submit_ele is not None: 
            submit_ele.click()
        
        # after a sucess login, 500px will automatically load the user's homefeed page. So after submitting the credentials, we
        # wait until one of an element in the login page become unavailable
        WebDriverWait(driver, time_out).until(EC.staleness_of(user_name_ele))
       
    except  NoSuchElementException:
        printR("Error accessing the login page. Please retry")
        return False
    except TimeoutException :
        printR(f'Time out while loading {user_inputs.user_name} home page. Please retry.')
        return False
    except:
        printR(f'Error loading {user_inputs.user_name} home page. Please retry.')
        return False  
    
    # username/password errors
    if check_and_get_ele_by_class_name(driver, 'error') is not None or \
       check_and_get_ele_by_class_name(driver, 'not_found') is not None or \
       check_and_get_ele_by_class_name(driver, 'missing') is not None:   
       printR(f'Error on loggin. Please retry with valid credentials')
       user_inputs.user_name = ''
       user_inputs.password = ''
       #Close_chrome_browser(driver)
       return False
    return True

#---------------------------------------------------------------
def Write_string_to_text_file(input_string, file_name, encode = ''):
    """Write the given string to a given text file. Create new file if it does not exist."""
    
    if not input_string or not file_name:
        return

    if encode == '':
        open_file = open(file_name, "w")
    else:
        open_file = open(file_name, "w", encoding = encode)

    open_file.write(input_string)
    open_file.close()

#--------------------------------------------------------------- 
def Show_html_result_file(file_name):
    """Offer the given html file with the default system app. """

    if not os.path.isfile(file_name):
         return

    file_path, file_extension = os.path.splitext(file_name)
    if file_extension == ".html":
        os.startfile(file_name)

#--------------------------------------------------------------- 
def Find_encoding(file_name):
    """Return the encoding of a given text file """
    import chardet
    r_file = open(file_name, 'rb').read()
    result = chardet.detect(r_file)
    charenc = result['encoding']
    return charenc 

#--------------------------------------------------------------- 
def CSV_photos_list_to_HTML(csv_file_name, output_lists, use_local_thumbnails = True, ignore_columns=[]):
    """Create a html file from a given photos list csv  file. Save it to disk and return the file name.

    Save the html file using the same name but with extension '.html'
    Expecting the first line to be the column headers, which are  no, page, id, title, link, src
    Hide the columns specified in the given IGNORE_COLUMNS LIST. The data in these columns are still being used to form the web link tag <a href=...>
    """
    CUSTOMED_COLUMN_WIDTHS = """
    <colgroup>
		<col style="width:4%">
		<col style="width:21%">
		<col span= "3" style="width:6%" >
		<col style="width:14%">	
		<col style="width:7%" >
		<col style="width:6%" >
		<col style="width:25%" >				
	</colgroup>
    """
    HEADER_STRING ="""
<head>
	<script charset="UTF-8" type = "text/javascript" src="javascripts/scripts.js"></script>
	<link   charset="UTF-8" type = "text/css" rel  = "stylesheet"  href = "css/styles.css" />
</head>""" 

# file name and extension check
    file_path, file_extension = os.path.splitext(csv_file_name)
    if file_extension != ".csv":
        return None

    html_file = file_path + '.html'
    avatars_folder    = os.path.basename(os.path.normpath(output_lists.avatars_dir))
    thumbnails_folder = os.path.basename(os.path.normpath(output_lists.thumbnails_dir))


    # Create the document description based on the given file name.
    # Ref: Photo list filename:  [path]\_[user name]\_[count]\_[types of document]\_[date].html
    # Example of filename: C:\ProgramData\500px_Apiless\Output\johndoe_16_photos_2019-06-17.html
    file_name = file_path.split('\\')[-1]
    splits = file_name.split('_')
    title_string = ''
    if len(splits) >=4:
        title_string = f'\
    <h2>Photo lists ({splits[1]})</h2>\n\
    <p> User / Date: {splits[0]} / {splits[-1]}</p>\n\
    <p> File: {html_file} </p>\n'

    with open(csv_file_name, newline='', encoding='utf-16') as csvfile:
        reader = csv.DictReader(row.replace('\0', '') for row in csvfile)
        headers = reader.fieldnames

        row_string = '\t<tr>\n'
        # Ref:
        # Columns    : 0   1   2            3     4               5                6      7      8         9                      10             11      12    13
        # Photo List : No, ID, Photo Title, Href, Thumbnail Href, Thumbnail Local, Views, Likes, Comments, Featured In Galleries, Highest Pulse, Rating, Date, Tags

        # write headers and assign sort method for appropriate columns   
        # each header cell has 2 DIVs: the left DIV for the header name, the right DIV for sort direction arrows     
        ignore_columns_count = 0
        for i, header in enumerate(reader.fieldnames):
            if header == 'Comments':
                header = 'Com-<br>ments'
            elif header == 'Highest Pulse':
                header = 'Highest<br>Pulse'    
                
            if header in ignore_columns:
                ignore_columns_count += 1
                continue  

            sort_direction_arrows = f"""
            <div class="hdr_arrows">
		        <div id ="arrow-up-{i-ignore_columns_count}">&#x25B2;</div>
		        <div id ="arrow-down-{i-ignore_columns_count}">&#x25BC;</div></div>"""

            left_div = f'''
            <div class="hdr_text">{header}</div>'''

            if header == "No":
                first_left_div = f'\t\t\t<div class="hdr_text">{header}</div>'
                # the No column is initially in ascending order, so we do not show the down arrow
                ascending_arrow_only = f"""
                <div class="hdr_arrows">
				    <div id ="arrow-up-{i-ignore_columns_count}">&#x25B2;</div>
				    <div id ="arrow-down-{i-ignore_columns_count}" hidden>&#x25BC;</div></div>"""
                row_string += f'\t\t<th onclick="sortTable({i-ignore_columns_count})">\n{first_left_div}{ascending_arrow_only}</th>\n'
            
            elif header == "Photo Title":
                row_string += f'\t\t<th onclick="sortTable({i-ignore_columns_count}, true)">{left_div}{sort_direction_arrows}</th>\n'

            else:
                row_string += f'\t\t<th onclick="sortTable({i-ignore_columns_count})">{left_div}{sort_direction_arrows}</th>\n'

        # write each row 
        row_string += '\t</tr>\n'
        for row in reader:
            row_string += '\t<tr>\n'
            for i in range(len(headers) ):
                col_header = headers[i]
                if col_header in ignore_columns:
                    continue  
                text = row[headers[i]]     
                # In Photo Tile column, show photo thumbnail and photo title with <a href> link
                if  col_header == 'Photo Title': 
                    if use_local_thumbnails:
                        photo_thumbnail = f"{thumbnails_folder}/{row['Thumbnail Local']}"
                    else:
                        photo_thumbnail = row['Thumbnail Href']
                    
                    # if photo thumbnail is empty, write an empty div to keep the same layout 
                    if (use_local_thumbnails and not row['Thumbnail Local']) or (not use_local_thumbnails and not row['Thumbnail Href']) :
                        row_string += f'\t\t<td><div"><div>{text}</div></div></td> \n' 
                    else:
                        photo_link =  row['Href']                 
                        row_string += f'\t\t<td>\n\t\t\t<div>\n\t\t\t\t<a href="{photo_link}" target="_blank">\n'
                        row_string += f'\t\t\t\t<img class="photo" src={photo_thumbnail}></a>\n'
                        row_string += f'\t\t\t\t<div><a href="{photo_link}" target="_blank">{text}</a></div></div></td>\n'
 

                elif  col_header == 'Tags':
                    row_string += f'\t\t<td class="alignLeft">{text}</td> \n' 
                
                elif  col_header == 'Featured In Galleries' and text != '':
                    # a gallery link has this format: https://500px.com/[photographer_name]/galleries/[gallery_name]
                    galleries = text.split(',')
                    if len(galleries) == 0:
                           row_string += f'\t\t<td></td>\n'
                    else:
                        row_string += f'\t\t<td>({len(galleries)}) \n'
                        for j, gallery in enumerate(galleries):
                            gallery_name = gallery[gallery.rfind('/') + 1:]    
                            row_string += f'\t\t\t<a href="{gallery}" target="_blank">{gallery_name}</a>'
                            if j < len(galleries) -1:
                                row_string += ',\n'                    
                        row_string += f'\t\t</td> \n'
                                
                else: 
                    row_string += f'\t\t<td>{text}</td> \n' 
            row_string += '\t</tr>\n'

        html_string = f'<html>\n{HEADER_STRING}\n\n<body> \n{title_string}<table> {CUSTOMED_COLUMN_WIDTHS}\n{row_string} </table>\n</body> </html>'

        #write html file 
        with open(html_file, 'wb') as htmlfile:
            htmlfile.write(html_string.encode('utf-16'))

    return html_file

#--------------------------------------------------------------- 
def CSV_to_HTML(csv_file_name, output_lists, use_local_thumbnails = True, ignore_columns=[]):
    """ Convert csv file of various types into html file and write it to disk . Return the saved html filename.
    
    Expected 5 csv files types: notifications list , unique users list, followers list, followings list, list of users who like a photo.
    The saved html file has the same name but with extension '.html' 
    Expecting first line is column headers, which varies depending on the csv types
    The argument IGNORE_COLUMNS is a list of the column headers for which we want to hide the entire column
    """
    if csv_file_name == '':
        return ''
    # file extension check
    file_path, file_extension = os.path.splitext(csv_file_name)
    if file_extension != ".csv":
        return ''

    HEADER_STRING = '''
<head>
	<script charset="UTF-8" type = "text/javascript" src="javascripts/scripts.js"></script>
	<link   charset="UTF-8" type = "text/css" rel  = "stylesheet"  href = "css/styles.css" />
</head>''' 

    html_full_file_name = file_path + '.html'

    avatars_folder    = os.path.basename(os.path.normpath(output_lists.avatars_dir))
    thumbnails_folder = os.path.basename(os.path.normpath(output_lists.thumbnails_dir))


    # Create document title and description based on these predefined file names:
    # Notifications   :    [user name]_[count]_notifications_                       [date].html
    # Unique users    :    [user name]_[count]_unique-users-last-n-notifications_   [date].html
    # Followers List  :    [user name]_[count]_followers_                           [date].html
    # Followings List :    [user name]_[count]_followings_                          [date].html
    # Users like photo:    [user name]_[count]_likes_[photo title]_                 [date].html

    file_name = file_path.split('\\')[-1]
    splits = file_name.split('_')  
    title, title_string = '', ''
    table_width =  'style="width:500"'
    if len(splits) >=4:
        if 'unique' in html_full_file_name:
            parts = splits[2].split('-')
            title = f'{splits[1]} unique users in the last {parts[-1]} notifications'
            table_width = 'style="width:310"'
        elif 'notifications' in html_full_file_name:
            title = f'Last {splits[1]} notifications'
            table_width =  'style="width:80%"'
        elif 'followers' in html_full_file_name:
            title = f'List of {splits[1]} followers'
        elif 'followings' in html_full_file_name:
            title = f'List of {splits[1]} followings'
            table_width = 'style="width:500"'
        elif 'likes' in html_full_file_name:
            title = f'List of {splits[1]} users who liked photo {splits[-2].replace("-", " ")}'
        
        title_string = f'\
    <h2>{title}</h2>\n\
    <p> User / Date: {splits[0]} / {splits[-1]}</p>\n\
    <p> File: {html_full_file_name} </p>\n'
 
    with open(csv_file_name, newline='', encoding='utf-16') as csvfile:
        reader = csv.DictReader(row.replace('\0', '') for row in csvfile)
        headers = reader.fieldnames
        if len(headers) < 4:
            printR(f'File {csv_file_name} is in wrong format!')
            return ''
        row_string = '\n\t<tr>\n'
  
        # write headers and assign sort method for appropriate columns   
        # each header cell has 2 parts: the left div for the header name, the right div for sort direction arrows     
        ignore_columns_count = 0
        for i, header in enumerate(reader.fieldnames):
            if header in ignore_columns:
                ignore_columns_count += 1
                continue

            sort_direction_arrows = f"""
            <div class="hdr_arrows">
		        <div id ="arrow-up-{i-ignore_columns_count}">&#x25B2;</div>
		        <div id ="arrow-down-{i-ignore_columns_count}">&#x25BC;</div></div>"""

            left_div = f"""
            <div class="hdr_text">{header}</div>"""
        
            if header == "No":
                first_left_div = f'\t\t\t<div class="hdr_text">{header}</div>'
                # the No column is initially in ascending order, so we do not show the down arrow
                ascending_arrow_only = f"""
                <div class="hdr_arrows">
				    <div id ="arrow-up-{i-ignore_columns_count}">&#x25B2;</div>
				    <div id ="arrow-down-{i-ignore_columns_count}" hidden>&#x25BC;</div>
			    </div>"""
                row_string += f'\t\t<th class="w40" onclick="sortTable({i-ignore_columns_count})">\n{first_left_div}{ascending_arrow_only}</th>\n'
            
            elif header == "Display Name":
                row_string += f"""\t\t<th class="w200" onclick="sortTable({i-ignore_columns_count}, 'sortByDisplayName')">{left_div}{sort_direction_arrows}</th>\n"""
            
            elif header == "Photo Title":
                row_string += f"""\t\t<th class="w200" onclick="sortTable({i-ignore_columns_count}, 'sortByPhotoTitle')">{left_div}{sort_direction_arrows}</th>\n"""
 
            elif header == "Followers" or header == "Count":
                row_string += f'\t\t<th class="w100" onclick="sortTable({i-ignore_columns_count})">{left_div}{sort_direction_arrows}</th>\n'
            
            elif header == "Status"or header == "Content":
                row_string += f'\t\t<th class="w210" onclick="sortTable({i-ignore_columns_count})">{left_div}{sort_direction_arrows}</th>\n'
            
            elif header == "Time Stamp":
                row_string += f'\t\t<th class="w120" onclick="sortTable({i-ignore_columns_count})">{left_div}{sort_direction_arrows}</th>\n'
            
            else:
                row_string += f'\t\t<th onclick="sortTable({i-ignore_columns_count})">{left_div}{sort_direction_arrows}</th>\n'

        # create rows for html table 
        row_string += '\t</tr>'       
        for row in reader:
            row_string += '\n\t<tr>\n'
            # Table columns vary depending on 4 different csv files:
            # Columns:         0   1            2             3             4          5   6          7                     8                      9            10          11      12 
            # Notifications  : No, Avatar Href, Avatar Local, Display Name, User Name, ID, Content,   Photo Thumbnail Href, Photo Thumbnail Local, Photo Title, Time Stamp, Status, Photo Link
      
            # Unique users   : No, Avatar Href, Avatar Local, Display Name, User Name, ID, Count,    
            # Followers List : No, Avatar Href, Avatar Local, Display Name, User Name, ID, Followers, Status
            # Followings List: No, Avatar Href, Avatar Local, Display Name, User Name, ID, Followers, Status

            for i in range(len(headers)): 
                col_header = headers[i]   
                # ignore unwanted columns
                if col_header in ignore_columns:
                    continue

                text = row[col_header]

                # In Display Name column, show user's avatar and the display name with link 
                if col_header == 'Display Name' : 
                    user_home_page = f'https://500px.com/{row["User Name"]}'        
                    user_name = row["Display Name"]

                    row_string += f'\t\t<td>\n\t\t\t<div>\n\t\t\t\t<a href="{user_home_page}" target="_blank">\n'
                    if use_local_thumbnails:
                        user_avatar =f"{avatars_folder}/{row['Avatar Local']}"
                    else:
                        user_avatar = row['Avatar Href']

                    row_string += f'\t\t\t\t<img src={user_avatar}></a>\n'
                    row_string += f'\t\t\t\t<div><a href="{user_home_page}" target="_blank">{user_name}</a></div></div></td>\n'

                    #row_string += f'\t\t<td>\n\t\t\t<div>\n\t\t\t\t<a href="{user_home_page}" target="_blank">\n'
                    #user_avatar = row['Avatar Local'] if use_local_thumbnails else row['Avatar Href']
                    #row_string += f'\t\t\t\t<img src={avatars_folder}/{user_avatar}></a>\n'
                    #row_string += f'\t\t\t\t<div><a href="{user_home_page}" target="_blank">{user_name}</a></div></div></td>\n'
               
                # Column 6:  Content, Count for Followers columns: 
                elif i == 6:  
                    row_string += f'\t\t<td>{text}</td> \n'
                    
                # Column 7 on Followers or Followings list 
                elif col_header == 'Status':
                    if text.find('Following') != -1: 
                        row_string += f'\t\t<td class="alignLeft" bgcolor="#00FF00">{text}</td> \n'   # green cell for following users                    
                    else:  
                        row_string += f'\t\t<td class="alignLeft">{text}</td> \n'          
  
                # In Photo Tile column, show photo thumbnail and photo title with <a href> link
                elif  col_header == 'Photo Title': 
                    if use_local_thumbnails:
                        photo_thumbnail = f"{thumbnails_folder}/{row['Photo Thumbnail Local']}"
                    else:
                        photo_thumbnail = row['Photo Thumbnail Href']
                    # if photo thumbnail is empty, write an empty div to keep the same layout 
                    if (use_local_thumbnails and not row['Photo Thumbnail Local']) or (not use_local_thumbnails and not row['Photo Thumbnail Href']) :
                        row_string += f'\t\t<td><div><div></div></div></td> \n'
                    else:
                        photo_link =  row['Photo Link']                 
                        row_string += f'\t\t<td>\n\t\t\t<div>\n\t\t\t\t<a href="{photo_link}" target="_blank">\n'
                        row_string += f'\t\t\t\t<img class="photo" src={photo_thumbnail}></a>\n'
                        row_string += f'\t\t\t\t<div>{text}</div></div></td>\n'

                # All other columns, write text as is
                else:                            
                     row_string += f'\t\t<td>{text}</td> \n'

            row_string += '\t</tr>'

        
        html_string = f'<html>\n{HEADER_STRING}\n\n<body>\n{title_string}<table {table_width}> {row_string} </ztable>\n</body> </html>'

        #write html file 
        with open(html_full_file_name, 'wb') as htmlfile:
            htmlfile.write(html_string.encode('utf-16'))

    return html_full_file_name

#--------------------------------------------------------------- 
# The getpass.win_getpass() does not work properly on Windows. We implement this for the desired effect.
# Credit: atbagga from https://github.com/microsoft/knack
def win_getpass(prompt='Password: ', stream=None):
    """Mask the passwork characters with * character, supporting the backspace key """
 
    shown_prompt=''
    for c in prompt:
        msvcrt.putwch(c)
        shown_prompt += c
    pw = ""
    while 1:
        c = msvcrt.getwch()
        if c == '\r' or c == '\n':
            break
        if c == '\003':
            raise KeyboardInterrupt
        if c == '\b':
            pw = pw[:-1]
            # rewrite the stdout
            shown_pwd = '*' * len(pw)
            shown_pwd += ' '    
            sys.stdout.write('\r' + shown_prompt + shown_pwd + '\b')
            sys.stdout.flush()
        else:
            msvcrt.putwch('*')
            pw = pw + c
   
    msvcrt.putwch('\r')
    msvcrt.putwch('\n')
    return pw

#--------------------------------------------------------------- 
def Validate_non_empty_input(prompt_message, user_inputs):
    """Prompt user for an input, make sure the input is not empty. Return True if Quit or Restart is requested. False otherwise """

    if 'password' in prompt_message:
        val = win_getpass(prompt=prompt_message)
    else:
        val = input(prompt_message)
    if val == 'q' or val == 'r':
        user_inputs.choice = val
        return val, True
    while len(val) == 0:        
        printR("Input cannot be empty! Please re-enter. Type 'q' to end or 'r' to restart")
        val = input(prompt_message)

    return val, False

#--------------------------------------------------------------- 
def Validate_input(prompt_message, user_inputs):
    """ Prompt for input and accepts nothing but digits or letter 'r' or 'q'. 
    Return the valid input and a boolean (True if r(estar)t or q(uit) is requested, False otherwise."""

    val = input(prompt_message) 
    while True:

        if val == 'r' or val == 'q':
            user_inputs.choice = val
            return val, True

        # if we have error converting inputs to integer, then the input is invalid
        try: 
            dummy_int = int(val)
            return val, False
        except ValueError:
            printR("Invalid input! Please retry.")
            val = input(prompt_message)


#--------------------------------------------------------------- 
def Get_IMG_element_from_homefeed_page(driver):
    """Get all <img> elements on page then remove elmenents that are not from user's friends.

    We want to get the list of loaded photos on the user home feed page, the ones from the photographers that you are following.
    Since all the class names in the user homefeed page are now postfixed with randomized texts, we will use the img tag as identifier for a photo, 
    from there, we remove non-interested img items such as avatars, thumbnails or recommended photos
    """
    # we are interested in items with the tag <img>
    img_eles = check_and_get_all_elements_by_tag_name(driver, 'img') 

    # img_eles list contains other img elements that we don't want, such as thumbnails, recommended photos..., we will remove them from the list
    for ele in reversed(img_eles):
        parent_4 = check_and_get_ele_by_xpath(ele, '../../../..') 
        if parent_4 is not None and parent_4.get_attribute('class').find('Elements__HomefeedPhotoBox') == -1:
            img_eles.remove(ele)
    return img_eles

#---------------------------------------------------------------
def update_progress(progress, message = ''):
    """Updates a text-based progress bar on the console.

    Accepts a float between 0 and 1. any int will be converted to a float.
    A value under 0 represents a 'halt'.
    A value at 1 or bigger represents 100%
    """
    if message == '':
        message = 'Progress'
    barLength = 15 # Modify this to change the length of the progress bar
    status = ""
    if isinstance(progress, int):
        progress = float(progress)
    if not isinstance(progress, float):
        progress = 0
        status = "error: progress var must be float\r\n"
    if progress < 0:
        progress = 0
        status = "Halt...\r\n"
    if progress >= 1:
        progress = 1
        status = "Done\r\n"
    block = int(round(barLength*progress))
    text = f'\r{message:<46.45}[{"."*block + " "*(barLength-block)}] {int(round(progress*100)):<3}% {status}'
    sys.stdout.write(text)
    sys.stdout.flush()

#---------------------------------------------------------------
def Hide_banners(driver):
    """Hide or close popup banners that make elements beneath them inaccessible. And click away the sign-in window if it pops up.
    
    Specifically, top banner is identified by the id 'hellobar',
    Bottom banners are identified by tag 'w-div' and
    Sign-up banner is identified by class 'join_500px_banner_close_ele'
    """

    top_banner = check_and_get_ele_by_id(driver, 'hellobar')
    if top_banner is not None:
        try:
            driver.execute_script("arguments[0].style.display='none'", top_banner)
        except:
            pass

    bottom_banners = check_and_get_all_elements_by_tag_name(driver, 'w-div')
    for banner in bottom_banners:
        close_ele = check_and_get_ele_by_tag_name(banner, 'span')
        if close_ele is not None:
            try:
                driver.execute_script("arguments[0].click();", close_ele)
            except:
                pass   

    join_500px_banner_close_ele = check_and_get_ele_by_class_name(driver, 'unified_signup__close')
    if join_500px_banner_close_ele is not None:
        try:
            driver.execute_script("arguments[0].click();", join_500px_banner_close_ele)
        except:
            pass

#---------------------------------------------------------------
def Show_menu(user_inputs, special_message=''):
    """ Display main menu. Validate and accept these inputs from users: user name, password  and the desired option. 
    
    - Inputs are stored in the user_inputs objects, which is passed by reference.  
    - The return value is a string containing either 'r', 'q' or any digit characters
    - The special_message, if given, will be displayed near the end of the menu. It could be used as an alert, warning or error
      from the last operation.
    """

    printC('')
    printC('--------- Chose one of these options: ---------')
    printY('      The following options require a user name:')
    printC('   1  Get user statistics')
    printC('   2  Get user photos list (login is optional)')
    printC('   3  Get followers list   (login is optional)')
    printC('   4  Get followings list ')
    printC('   5  Get a list of users who liked a given photo (login is optional)')

    printC('')
    printY('      The following options require user login:')
    printC('   6  Get n last notifications (max 5000) and the unique users on it')
    printC('   7  Check if a user is following you')
    printC('')
    printC('   8  Like n photos from a given user')
    printC('   9  Like n photos, starting at a given index, on various photo pages') 
    printC('  10  Like n photos of each user who likes a given photo or yours')
    printC('  11  Like n photos from your home-feed page, excluding recommended photos ')
    printC('  12  Like n photos of each users in your last m notifications')
    printC('')
    printY('      The following option does not need credentials:')
    printC('  13  Play slideshow on a given gallery (login is optional)')
    printC('')
    printC('   r  Restart with different user')
    printC('   q  Quit')
    printC('')
  
    if special_message:
        printY(special_message)
  
    sel, abort = Validate_input('Enter your selection >', user_inputs)

    if abort:
        return 

    sel = int(sel)
    # play slideshow, no credentials needed
    if sel == 13:
        user_inputs.choice = str(sel)
        return 
    
    # user name is mandatory
    if user_inputs.user_name == '':
        user_inputs.user_name = input('Enter 500px user name >')
    printG(f'Current user: {user_inputs.user_name}')

    # password is optional:
    #  - 2  Get user photos list: if logged in, we can get the list of galleries that each of your photo is featured in
    #  - 3  Get followers list: if logged in, we can get your following status to each of your followers
    #  - 5  Get a list of users who liked a given photo: if logged in, we can get your following status to each user in the list
    if (sel == 2 or sel == 3 or sel == 5) and user_inputs.password == '':
        prompt_message = 'Optional: you can get info in greater detail if you log in,\npress ENTER to ignore this option, or type in the password now >'
        expecting_password = win_getpass(prompt=prompt_message)
        if expecting_password != 'q' and expecting_password != 'r':
            user_inputs.password = expecting_password
        else:
            user_inputs.choice = expecting_password
            return 
            
    if sel < 6 or sel == 7:
        user_inputs.choice = str(sel)
        return
    
    # password is mandatory ( quit or restart are also possible at this step )
    if sel >= 6 and sel <= 15:
        if user_inputs.user_name == '':
            user_inputs.user_name, abort = Validate_non_empty_input('Enter 500px user name >', user_inputs)
            if abort:
                return

        if user_inputs.password == '':
            user_inputs.password, abort =  Validate_non_empty_input('Enter password >', user_inputs)
            if abort:
                return
    
    user_inputs.choice = str(sel)        

#---------------------------------------------------------------
def Show_galllery_selection_menu(user_inputs):
    """ Menu to select a photo gallery for slideshow. Allow the user to abort during the input reception.
        Return three values: the photo href, the gallery name, and a boolean of True if an abort is requested, False otherwise. """

    printC('--------- Select the desired photos gallery: ---------')
    printC('    1  Popular')
    printC('    2  Popular-Undiscovered photographers')
    printC('    3  Upcoming')
    printC('    4  Fresh')
    printC("    5  Editor's Choice")
    printC("    6  User-specified gallery ...")
    # option to play slideshow on user's photos if a user name was provided 
    if user_inputs.choice == '13' and  user_inputs.user_name: 
        printC("    7  My photos")

    printC('')
    printY('    r  Restart for different user')
    printY('    q  Quit')

    sel = input('Enter your selection >')
    # exit the program
    if sel == 'q' or sel == 'r':
        user_inputs.choice = sel
        return sel, '', True

    elif sel == '1': return 'https://500px.com/popular'                       , 'Popular', False
    elif sel == '2': return 'https://500px.com/popular?followers=undiscovered', 'Popular, Undiscovered', False
    elif sel == '3': return 'https://500px.com/upcoming'                      , 'Upcoming', False
    elif sel == '4': return 'https://500px.com/fresh'                         , 'Fresh', False
    elif sel == '5': return 'https://500px.com/editors'                       , "Editor's Choice", False
    elif sel == '6': 
        input_val, abort = Validate_non_empty_input('Enter the link to your desired photo gallery.\n\
 It could be a public gallery with filters, or a private gallery >', user_inputs)
        if abort:
            return '', '', True
        else:
            return input_val, 'User-specified gallery', False


    elif sel == '7': return f'https://500px.com/{user_inputs.user_name}'                  , 'My photos', False

    else:
        Show_galllery_selection_menu(user_inputs)
#---------------------------------------------------------------
def Define_and_read_command_line_arguments(): 
    """ Define all optional user inputs and their default values. Then fill in with the actual values from command lines.
        Return a user_inputs objects filled with given arguments. 

    All command line arguments are optional (as opposed to postional).  If the argurment '--choice' is not set, all other arguments will be ignored whether 
    they are set or not, and the attribute "use_command_line_args" will be set to false 
    """
    
    user_inputs = User_inputs()
    #define arguments and their default values
    ap = argparse.ArgumentParser()
    ap.add_argument("-c",  "--choice",                      required=False,           nargs='?', const=1, default='0', help="User selection(1-14)") #to set default value, add:  nargs='?', const=1, default=0
    ap.add_argument("-u",  "--user_name",                   required=False,           nargs='?', const=1, default='',  help="500px user name")
    ap.add_argument("-d",  "--password",                    required=False,           nargs='?', const=1, default='',  help="Password for current user")
    ap.add_argument("-p",  "--photo_href",                  required=False,           nargs='?', const=1, default='',  help="")
    ap.add_argument("-g",  "--gallery_href",                required=False,           nargs='?', const=1, default='',  help="")
    ap.add_argument("-l",  "--number_of_photos_to_be_liked",required=False, type=int, nargs='?', const=1, default=1,   help="")
    ap.add_argument("-i",  "--index_of_start_photo",        required=False, type=int, nargs='?', const=1, default=1,   help="")
    ap.add_argument("-n",  "--number_of_notifications",     required=False, type=int, nargs='?', const=1, default=200, help="")
    ap.add_argument("-a",  "--target_user_name",            required=False,           nargs='?', const=1, default='',  help="")
    ap.add_argument("-t",  "--time_interval",               required=False, type=int, nargs='?', const=1, default=4,   help="")   

      # read actual command line arguments
    args_dict= vars(ap.parse_args())
    for dict_name in args_dict:
        if DEBUG:
            print(f'    {dict_name}: {args_dict[dict_name]}')
        setattr(user_inputs, dict_name, args_dict[dict_name])
    # if a choice is provided from the command line, we will switch to command line mode. 
    if user_inputs.choice != '0':
        user_inputs.use_command_line_args = True
    return user_inputs
#---------------------------------------------------------------
def Get_additional_user_inputs(user_inputs):
    """ Ask the user for additional inputs based on the option previously selected in user_inputs.choice.  

    Allow the user to abort (quit or restart) anytime during the input reception. return false if aborting, true otherwise """

    if user_inputs.choice == 'q' or user_inputs.choice == 'r':
        return False

    # no additional input are required for options from 1 to 5
    choice = int(user_inputs.choice)
    if choice < 5:
        return True
 
    # 5. Get a list of users who liked a given photo: photo_href
    if choice == 5: 
        user_inputs.photo_href, abort = Validate_non_empty_input('Enter your photo href >', user_inputs)
        if abort:
            return False

    # 6. Get n last notifications (max 5000) and the unique users on it: number_of_notifications 
    if choice == 6 : 
        input_val, abort =  Validate_input(f'Enter the number of notifications you want to retrieve(max {MAX_NOTIFICATION_REQUEST}) >', user_inputs)
        if abort: 
            return False
        else:
            num = int(input_val)
            user_inputs.number_of_notifications = num if num < MAX_NOTIFICATION_REQUEST else MAX_NOTIFICATION_REQUEST
  
    # 7. Check if a user is following you : target user name
    elif choice == 7:
        user_inputs.target_user_name , abort =  Validate_non_empty_input('Enter target user name >', user_inputs)
        if abort:
            return False  

    # common input for 8 to 11: number of photo to be auto-liked
    elif choice >= 8 and choice <= 11:
        input_val, abort =  Validate_input('Enter the number of photos you want to auto-like >', user_inputs)
        if abort:
            return False
        else: 
            num = int(input_val)
            user_inputs.number_of_photos_to_be_liked = num if num < MAX_AUTO_LIKE_REQUEST else MAX_AUTO_LIKE_REQUEST         

        # 8.  Like n photos from a given user: target_user_name
        if choice == 8: 
            user_inputs.target_user_name, abort = Validate_non_empty_input('Enter target user name >', user_inputs)
            if abort:
                return False  

        # 9.  Like n photos, starting at a given index, on various photo pages:  gallery_href, index_of_start_photo
        elif choice == 9:  
            # gallery selection
            user_inputs.gallery_href, user_inputs.gallery_name, abort = Show_galllery_selection_menu(user_inputs)
            if abort:
                return False
            
            input_val, abort =  Validate_input('Enter the index of the start photo (1-500) >', user_inputs)
            if abort:
                return False  
            else: 
                user_inputs.index_of_start_photo = int(input_val)

        # 10.  Like n photos of each user who likes a given photo or yours:
        elif choice == 10: 
            #photo_href
            user_inputs.photo_href, abort =  Validate_non_empty_input('Enter your photo href >', user_inputs)
            if abort: 
                return False    
            # these additional options are for next version
            ## index_of_start_user
            #input_val, abort =  Validate_input('Enter the start index of the user (default 1)>' , user_inputs)
            #if abort:
            #    return False  
            #else: 
            #    int_val = int(input_val)
            #    # the end user will use 1-based index, so we will convert the input to 0-based
            #    if int_val > 0: int_val -= 1
            #    user_inputs.index_of_start_user = int_val   
            
            ## number of users    
            #input_val, abort =  Validate_input('Enter the number of users you want to process>' , user_inputs)
            #if abort:
            #    return False  
            #else: 
            #    int_val = int(input_val)
            #    user_inputs.number_of_users = int_val        
    
    # 12. Like n photos of each users in your last m notifications         
    elif choice == 12: 
        input_val, abort =  Validate_input(f'Enter the number of notifications you want to process(max {MAX_NOTIFICATION_REQUEST}) >', user_inputs)
        if abort: 
            return False
        else: 
            num = int(input_val)
            user_inputs.number_of_notifications = num if num < MAX_NOTIFICATION_REQUEST else MAX_NOTIFICATION_REQUEST

        input_val, abort =  Validate_input('Enter the number of photos you want to auto-like for each user >', user_inputs)
        if abort:
            return False
        else: 
            num = int(input_val)
            user_inputs.number_of_photos_to_be_liked = num if num < MAX_AUTO_LIKE_REQUEST else MAX_AUTO_LIKE_REQUEST

    # 13.  Play slideshow on a given gallery 
    elif choice == 13:
        # allow a login for showing NSFW contents
        if user_inputs.user_name == '':
            printY('If you want to show NSFW contents, you need to login.\n Type your user name now or just press ENTER to ignore')
            user_inputs.user_name = input('>')
            if user_inputs.user_name == 'q' or user_inputs.user_name == 'r':
                user_inputs.choice = user_inputs.user_name
                return False               
        if user_inputs.user_name is not '' and user_inputs.password is '':                   
            user_inputs.password, abort = Validate_non_empty_input('Type your password> ', user_inputs)
            if abort:
                return False        

        user_inputs.gallery_href, user_inputs.gallery_name, abort = Show_galllery_selection_menu(user_inputs)
        if abort:
            return False

        input_val, abort = Validate_input('Enter the interval time between photos, in second>', user_inputs)
        if abort:
            return False
        else:
            user_inputs.time_interval = int(input_val)

            printY(f'Slideshow {user_inputs.gallery_name} will play in fullscreen, covering this control window.\n To stop the slideshow before it ends, and return to this window, press ESC three times.\n Now press ENTER to start >')

            wait_for_enter_key = input() 
 
    # 14. (in progress) Get following statuses of users you are following ( user_name, start index, number_of_users)
    # 15. Like n photos from each of m users, starting at a given start index, from a given csv files
    elif choice == 14 or choice == 15:
        # number of followers
        input_val, abort =  Validate_input('Enter the number of followers you want to process >', user_inputs)
        if abort:
            return False  
        else: 
            user_inputs.number_of_users = int(input_val)

        # start index of the user
        input_val, abort =  Validate_input('Enter the user start index (1-based)>' , user_inputs)
        if abort:
            return False  
        else: 
            int_val = int(input_val)
            # the end user will use 1-based index, so we will convert the input to 0-based
            if int_val > 0: int_val -= 1
            user_inputs.index_of_start_user = int_val 

        
        if choice == 15:
            #number of photos
            input_val, abort =  Validate_input('Enter the number of photos you want to auto-like >', user_inputs)
            if abort:
                return False
            else: 
                num = int(input_val)
                user_inputs.number_of_photos_to_be_liked = num if num < MAX_AUTO_LIKE_REQUEST else MAX_AUTO_LIKE_REQUEST 
        
            # full file name of the cvs file 
            user_inputs.csv_file, abort =  Validate_non_empty_input('Enter the csv full file name>', user_inputs)
            if abort: 
                return False       
            else:
                user_inputs.csv_file =user_inputs.csv_file.replace("\"", "").replace("\'", "") 
        return True
 
#---------------------------------------------------------------
def Handle_option_1(driver, user_inputs, output_lists):
    """ Get user status."""

    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.strftime(DATE_FORMAT)
    printG(f"Getting user's statistics:")

    # do task
    #driver = Start_chrome_browser(headless_mode = HEADLESS_MODE) 
    
    stats, error_message = Get_stats(driver, user_inputs, output_lists) 
    if error_message:
        printR(error_message)
        #Close_chrome_browser(driver)
        if user_inputs.use_command_line_args == False:
            Show_menu(user_inputs, error_message)
            return
    
    # write result to html file, show it on browser
    html_file =  os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_stats_{date_string}.html')
    Write_string_to_text_file(Create_user_statistics_html(stats), html_file, 'utf-16')
    #Close_chrome_browser(driver)
    Show_html_result_file(html_file)

    # print summary report
    time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
    print(f' The process took {time_duration} seconds') 

#---------------------------------------------------------------
def Handle_option_2(driver, user_inputs, output_lists):
    """ Get user photos """

    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.strftime(DATE_FORMAT)

    printG(f"Getting {user_inputs.user_name}'s photos list:")
    # avoid to do the same thing twice: if list (in memory) has items AND output file (on disk) exists
    if output_lists.photos is not None and len(output_lists.photos) > 0:
        html_file = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{len(output_lists.photos)}_photos_{date_string}.html')
        if  os.path.isfile(html_file):
            printY(f'Results exists in memory and on disk. Showing the existing file at:\n{os.path.abspath(html_file)} ...')
            Show_html_result_file(html_file)
            ans = input('This file will be overidden if you want to redo. Proceed ? (y/n)')
            if ans == 'n' : 
                return

    # do the action
    #driver = Start_chrome_browser(headless_mode = HEADLESS_MODE) 
    # if user provided password then login (logged-in users can see the galleries that feature theirs photos

    if user_inputs.password != '' and not Logged_in(driver):
        if Login(driver, user_inputs) == False :
            #Close_chrome_browser(driver)
            return

    Hide_banners(driver)
    output_lists.photos, error_message = Get_photos_list(driver, user_inputs, output_lists)
    #Close_chrome_browser(driver)
    if error_message:
        printR(error_message)
        if len(output_lists.photos) == 0:
            return


    # write result to csv, convert it to html, show html in browser
    if output_lists.photos is not None and len(output_lists.photos) > 0:
        csv_file = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{len(output_lists.photos)}_photos_{date_string}.csv')           
        if Write_photos_list_to_csv(user_inputs.user_name, output_lists.photos, csv_file) == True:
            html_file = CSV_photos_list_to_HTML(csv_file, output_lists, use_local_thumbnails = USE_LOCAL_THUMBNAIL,  
                                                ignore_columns = ['ID', 'Href', 'Thumbnail Href', 'Thumbnail Local', 'Rating'])
            Show_html_result_file(html_file)  
            
            time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
            print(f' The process took {time_duration} seconds') 
        else:
            printR(f'    Error writing the output file\n:{csv_file}')

#---------------------------------------------------------------
def Handle_option_3(driver, user_inputs, output_lists):
    """ Get followers"""
    
    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.strftime(DATE_FORMAT)
    printG(f"Getting the list of users who follow {user_inputs.user_name}:")

    # avoid to do the same thing twice: when the list (in memory) has items and output file exists on disk
    if output_lists.followers_list is not None and len(output_lists.followers_list) > 0:
        html_file = f'{user_inputs.user_name}_{len(output_lists.followers_list)}_followers_{date_string}.html'
        if os.path.isfile(html_file):
            printY(f'Results exists in memory and on disk. Showing the existing file at:\n{os.path.abspath(html_file)} ...')
            Show_html_result_file(html_file) 
            return
   
    # do task
    #driver = Start_chrome_browser(headless_mode = HEADLESS_MODE) 
    # if user provided password then login
    if user_inputs.password != '' and not Logged_in(driver):
        if Login(driver, user_inputs) == False :
            #Close_chrome_browser(driver)            
            return

    Hide_banners(driver)
    output_lists.followers_list = Get_followers_list(driver, user_inputs, output_lists)
    #Close_chrome_browser(driver)

    # write result to csv, convert it to html, show html in browser
    if output_lists.followers_list is not None and len(output_lists.followers_list) > 0:
        csv_file = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{len(output_lists.followers_list)}_followers_{date_string}.csv')           
        if Write_users_list_to_csv(output_lists.followers_list, csv_file) == True:
            # show output and print summary report
            html_file = CSV_to_HTML(csv_file, output_lists, use_local_thumbnails = USE_LOCAL_THUMBNAIL, 
                                    ignore_columns=['Avatar Href', 'Avatar Local', 'User Name', 'ID'])
            Show_html_result_file(html_file) 
            time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
            print(f' The process took {time_duration} seconds') 
        else:
            printR(f'    Error writing the output file\n:{csv_file}')
#---------------------------------------------------------------
def Handle_option_4(driver, user_inputs, output_lists):
    """ Get followings (friends)"""
    
    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.strftime(DATE_FORMAT)
    printG(f"   Getting the list of users that you are following:")

    # avoid to do the same thing twice: when the list (in memory) has items and output file exists on disk
    if output_lists.followings_list is not None and len(output_lists.followings_list) > 0:
        # find the latest html file on disk and show it
        files = [f for f in glob.glob(output_lists.output_dir + f"**/{user_inputs.user_name}*followings*.html")]
        files.sort(key=lambda x: os.path.getmtime(x))
        html_file = files[-1]
        if os.path.isfile(html_file):
            printY(f'Results exist in memory and on disk. Showing the existing file:\n{os.path.abspath(html_file)} ...')
            Show_html_result_file(html_file) 
            return

    # do task
    #driver = Start_chrome_browser(headless_mode = HEADLESS_MODE) 
    output_lists.followings_list = Get_followings_list(driver, user_inputs, output_lists)
    #Close_chrome_browser(driver)

    # write result to csv, convert it to html, show html in browser
    if len(output_lists.followings_list) > 0:
        csv_file = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{len(output_lists.followings_list)}_followings_{date_string}.csv')
        if Write_users_list_to_csv(output_lists.followings_list, csv_file) == True:
            # show output and print summary report
            html_file = CSV_to_HTML(csv_file, output_lists, use_local_thumbnails = USE_LOCAL_THUMBNAIL, 
                                    ignore_columns = ['Avatar Href', 'Avatar Local', 'User Name', 'ID', 'Status'])
            Show_html_result_file(html_file) 
            time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
            print(f' The process took {time_duration} seconds') 
        else:
            printR(f'    Error writing the output file\n:{csv_file}')

#---------------------------------------------------------------
def Handle_option_5(driver, user_inputs, output_lists):
    """ Get a list of users who liked a given photo."""
    
    time_start = datetime.datetime.now().replace(microsecond=0) 
    #driver = Start_chrome_browser(headless_mode = HEADLESS_MODE)       
    printG(f"Getting the list of unique users who liked the given photo:")

    # if user provided password then login
    if user_inputs.password != '' and not Logged_in(driver):
        if Login(driver, user_inputs) == False :
            #Close_chrome_browser(driver)    
            return

    try:
        driver.get(user_inputs.photo_href)
    except:
        printR(f'Invalid href: {user_inputs.photo_href}. Please retry.')
        #Close_chrome_browser(driver)
        Show_menu(user_inputs)        
        return

    # do task
    time.sleep(1)
    Hide_banners(driver)
    output_lists.like_actioners_list, csv_file = Get_like_actioners_list(driver, output_lists)
    #Close_chrome_browser(driver)

    # write result to csv, convert it to html, show html in browser
    if output_lists.like_actioners_list is not None and \
       len(output_lists.like_actioners_list) > 0 and \
       Write_users_list_to_csv(output_lists.like_actioners_list, csv_file) == True:
        html_file = CSV_to_HTML(csv_file, output_lists, use_local_thumbnails = USE_LOCAL_THUMBNAIL,  
                                ignore_columns = ['Avatar Href', 'Avatar Local', 'User Name', 'ID'])
        Show_html_result_file(html_file) 

    # print summary report
    time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
    print(f' The process took {time_duration} seconds') 
#---------------------------------------------------------------
def Handle_option_6(driver, user_inputs, output_lists):
    """ Get n last notifications details (max 5000). Show the detail list and the list of the unique users on it"""

    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.strftime(DATETIME_FORMAT)
    if user_inputs.number_of_notifications == -1:
        printG(f"Getting up to {MAX_NOTIFICATION_REQUEST} notifications and the unique users on that list:")
    else: 
        printG(f"Getting the last {user_inputs.number_of_notifications} notifications and the unique users on that list:")
    #csv_file = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{user_inputs.number_of_notifications}_notifications_{date_string}.csv')
    html_file = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{user_inputs.number_of_notifications}_notifications_{date_string}.html')

    # avoid to do the same thing twice: when the list (in memory) has items and output file exists on disk
    if output_lists.notifications is not None and len(output_lists.notifications) > 0 and os.path.isfile(html_file):
        printY(f'    Results exists in memory and on disk. Showing the existing file at:\n{os.path.abspath(html_file)} ...')        
        Show_html_result_file(html_file)
        return
    
    if not Logged_in(driver):
        if Login(driver, user_inputs) == False :
            #Close_chrome_browser(driver)
            return

    driver.get('https://500px.com/notifications')
    time.sleep(1)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    # abort the action if the target objects failed to load within a given timeout        
    if not Finish_Javascript_rendered_body_content(driver, time_out=30, class_name_to_check='finished')[0]:
        return	

    Hide_banners(driver)

    # do task   
    output_lists.notifications, output_lists.unique_notificators = Get_notification_list(driver, user_inputs, output_lists, True)
        
    if len(output_lists.notifications) == 0 and len(output_lists.unique_notificators) == 0:
        Show_menu(user_inputs)
        #Close_chrome_browser(driver)
        return

    #Close_chrome_browser(driver)
    
    csv_file = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{len(output_lists.notifications)}_notifications_{date_string}.csv')
    html_file = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{user_inputs.number_of_notifications}_notifications_{date_string}.html')

    # write unique users list to csv. Convert it to html, show it in browser
    csv_file_unique_users  = os.path.join(output_lists.output_dir, \
        f"{user_inputs.user_name}_{len(output_lists.unique_notificators)}_unique-users-in-last-{len(output_lists.notifications)}_notifications_{date_string}.csv")
    if len(output_lists.unique_notificators) > 0 and  Write_unique_notificators_list_to_csv(output_lists.unique_notificators, csv_file_unique_users) == True:
        html_file = CSV_to_HTML(csv_file_unique_users, output_lists, use_local_thumbnails = USE_LOCAL_THUMBNAIL,  
                                ignore_columns = ['Avatar Href', 'Avatar Local', 'User Name', 'ID'])
        Show_html_result_file(html_file)     
    
    # Write the notification list to csv. Convert it to html, show it in browser        
    if len(output_lists.notifications) > 0 and  Write_notifications_to_csvfile(output_lists.notifications, csv_file) == True:
        html_file = CSV_to_HTML(csv_file, output_lists, use_local_thumbnails = USE_LOCAL_THUMBNAIL, 
                                ignore_columns = ['Avatar Href', 'Avatar Local', 'User Name', 'ID', 'Photo Thumbnail Href', 'Photo Thumbnail Local', 'Photo Link'])
        Show_html_result_file(html_file) 

    # print summary report
    time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
    print(f' The process took {time_duration} seconds') 
#---------------------------------------------------------------
def Handle_option_7(driver, user_inputs, output_lists):
    """Check if a user is following you."""

    time_start = datetime.datetime.now().replace(microsecond=0)
    printG(f"Check if user {user_inputs.target_user_name} follows {user_inputs.user_name}:")

    # do task
    #driver = Start_chrome_browser(headless_mode = HEADLESS_MODE) 
    result, message = Does_this_user_follow_me(driver, user_inputs)

    if result == True:
        printG(message)
    else:
        printR(message) if 'User name not found' in message else printR(message)
    
    #Close_chrome_browser(driver)

    # print summary report
    time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
    print(f' The process took {time_duration} seconds') 
#---------------------------------------------------------------
def Handle_option_8(driver, user_inputs, output_lists):
    """ Like n photos from a given user."""

    time_start = datetime.datetime.now().replace(microsecond=0)
    printG(f"Starting auto-like {user_inputs.number_of_photos_to_be_liked} photo(s) of user {user_inputs.target_user_name}:")
    #driver = Start_chrome_browser(headless_mode = HEADLESS_MODE) 
    if not Logged_in(driver):
        if Login(driver, user_inputs) == False :
            #Close_chrome_browser(driver)
            return

    
    # do task   
    Like_n_photos_from_user(driver, user_inputs.target_user_name, user_inputs.number_of_photos_to_be_liked, include_already_liked_photo_in_count=True, close_browser_on_error = False) 
    #Close_chrome_browser(driver)

    # print summary report
    time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
    print(f' The process took {time_duration} seconds') 
#---------------------------------------------------------------
def Handle_option_9(driver, user_inputs, output_lists):
    """Like n photos, starting at a given index, on various photo pages ."""

    time_start = datetime.datetime.now().replace(microsecond=0)
    printG(f"Like {user_inputs.number_of_photos_to_be_liked} photo(s) from {user_inputs.gallery_name} gallery, start at index {user_inputs.index_of_start_photo}:")
    #driver = Start_chrome_browser(headless_mode = HEADLESS_MODE) 
    
    if not Logged_in(driver): 
        if Login(driver, user_inputs) == False :
            #Close_chrome_browser(driver)
            return
    
    driver.get(user_inputs.gallery_href)
    time.sleep(2)

    # abort the action if the target objects failed to load within a given timeout    
    #if not Finish_Javascript_rendered_body_content(driver, time_out=15, class_name_to_check = 'entry-visible')[0]:
    #    return None, None	
    innerHtml = driver.execute_script("return document.body.innerHTML")  
    time.sleep(2)

    Hide_banners(driver)

    # do task
    Like_n_photos_on_current_page(driver, user_inputs.number_of_photos_to_be_liked, user_inputs.index_of_start_photo)
   # Close_chrome_browser(driver)

    # print summary report
    time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
    print(f' The process took {time_duration} seconds') 
#---------------------------------------------------------------
def Handle_option_10(driver, user_inputs, output_lists):
    """Like n photos of each user who likes a given photo or yours."""

    time_start = datetime.datetime.now().replace(microsecond=0)
    printG(f"   Like {user_inputs.number_of_photos_to_be_liked} photos of each user who liked the photo:")
    print(f'    Getting the list of users who liked the photo ...')
    #driver = Start_chrome_browser(headless_mode = HEADLESS_MODE) 
    if not Logged_in(driver):
        if Login(driver, user_inputs) == False :
            #Close_chrome_browser(driver)
            return
    try:
        driver.get(user_inputs.photo_href)
    except:
        printR(f'    Invalid href: {user_inputs.photo_href}. Please retry.')
        #Close_chrome_browser(driver)
        Show_menu(user_inputs)         
        return

    time.sleep(1)
    Hide_banners(driver)        

    # do preliminary task: get the list of users who liked your given photo
    output_lists.like_actioners_list, dummy_file_name = Get_like_actioners_list(driver, output_lists)
    if len(output_lists.like_actioners_list) == 0: 
        #printG(f'The photo {photo_tilte} has no affection yet')
        Show_menu(user_inputs)
        return 
    actioners_count = len(output_lists.like_actioners_list)
    include_already_liked_photo_in_count = True  # meaning: if you want to autolike 3 first photos, and you found out two of them are already liked, then you need to like just one photo.
                                                    # if this is set to False, then you will find 3 available photos and Like them 

    # do main task
    # we may have option to process only part of the users list. 
    # Since the list may be quite large and we don't want to stress the server by sending too many requests. 
    #start_index = max(0, user_inputs.index_of_start_user)
    #end_index   = min(start_index + user_inputs.number_of_users, len(output_lists.like_actioners_list) - 1)
    #for i, actor in enumerate(output_lists.like_actioners_list[start_index : end_index]):  

    for i, actor in enumerate(output_lists.like_actioners_list):  
        print(f'    User {str(i+1)}/{actioners_count}: {actor.display_name}, {actor.user_name}')
        Like_n_photos_from_user(driver, actor.user_name, user_inputs.number_of_photos_to_be_liked, include_already_liked_photo_in_count, close_browser_on_error=False)
    #Close_chrome_browser(driver)

    # print summary report
    time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
    print(f' The process took {time_duration} seconds') 
#---------------------------------------------------------------
def Handle_option_11(driver, user_inputs, output_lists):
    """Like n friend's photos in homefeed page."""
    
    time_start = datetime.datetime.now().replace(microsecond=0)
    printG(f"Like {user_inputs.number_of_photos_to_be_liked} photos from the {user_inputs.user_name}'s home feed page:")
    #driver = Start_chrome_browser(headless_mode = HEADLESS_MODE) 
    if not Logged_in(driver):
        if Login(driver, user_inputs) == False :
            #Close_chrome_browser(driver)
            return
    else:
        # make sure the current page is user's homefeed page 
        driver.get('https://500px.com')
        time.sleep(1)        
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    # after a success login, the user's the homefeed page will automatically open     
    # we may consider this: abort the action if the photos fail to load within a given timeout    
    #if not Finish_Javascript_rendered_body_content(driver, time_out=30, class_name_to_check='finished')[0]:
    #  return None, None	    
  
    Hide_banners(driver) 
 
    # do task
    Like_n_photos_on_homefeed_page(driver, user_inputs)     
    #Close_chrome_browser(driver)

    # print summary report
    time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
    print(f' The process took {time_duration} seconds') 
#---------------------------------------------------------------
def Handle_option_12(driver, user_inputs, output_lists):
    """Like n photos of each user in the last m notifications.  """

    time_start = datetime.datetime.now().replace(microsecond=0)
    #driver = Start_chrome_browser(headless_mode = HEADLESS_MODE) 
    printG(f"Like n photos of each user in the last m notifications:")
    print(f'    Getting the list of unique users in the last {user_inputs.number_of_notifications} notifications ...')
    if not Logged_in(driver):
        if Login(driver, user_inputs) == False :
            #Close_chrome_browser(driver)
            return
    driver.get('https://500px.com/notifications')
    time.sleep(1)        

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    
    # abort the action if the target objects failed to load within a given timeout    
    if not Finish_Javascript_rendered_body_content(driver, time_out=30, class_name_to_check='finished')[0]:
      return None, None	

    Hide_banners(driver)  
       
    # do preliminary task
    output_lists.unique_notificators = Get_notification_list(driver, user_inputs, output_lists, True)[1]

    # do main task
    users_count = len(output_lists.unique_notificators)
    print(f"    Starting auto-like {user_inputs.number_of_photos_to_be_liked} photos of each of {users_count} users on the list ...")
    
    for i, notification_element in enumerate(output_lists.unique_notificators):
        notif_items = notification_element.split(',')
        # unique notificator element:
        # 0   1            2             3             4          5   6         
        # No, Avatar Href, Avatar Local, Display Name, User Name, ID, Count       
        if len(notif_items) > 4: 
            print(f'    User {notif_items[0]}/{users_count}: {notif_items[3]}, {notif_items[4]}')
            Like_n_photos_from_user(driver, notif_items[4], user_inputs.number_of_photos_to_be_liked, include_already_liked_photo_in_count=True, close_browser_on_error=False)
    #Close_chrome_browser(driver)

    # print summary report
    time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
    print(f' The process took {time_duration} seconds') 
#---------------------------------------------------------------
def Handle_option_13(driver, user_inputs, output_lists):
    """ Play slideshow on a given gallery. """

    time_start = datetime.datetime.now().replace(microsecond=0)
    printG("Playing the slideshow ...")

    # open a new Chrome Driver with specific options for playing the slideshow (we are not using the passed driver)
    chrome_options = Options()  
    chrome_options.add_argument('--kiosk')   
    chrome_options.add_argument('--hide-scrollbars')   
    chrome_options.add_experimental_option("excludeSwitches", ['enable-automation']);
    
    driver_with_GUI = webdriver.Chrome(options=chrome_options)
    # login if credentials are provided
    if user_inputs.user_name !='' and user_inputs.password != '':
        if Login(driver_with_GUI, user_inputs) == False :
            printR('Error logging in. Slideshow will be played without a user login.')  
        
    driver_with_GUI.get(user_inputs.gallery_href)
    driver_with_GUI.execute_script("return document.body.innerHTML")
    time.sleep(1)
    Hide_banners(driver_with_GUI)

    # do task
    Play_slideshow(driver_with_GUI, int(user_inputs.time_interval))
    
    # print summary report
    time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
    print(f'    The slideshow played in {time_duration} seconds') 
    Close_chrome_browser(driver_with_GUI)

#---------------------------------------------------------------
# EXTRA OPTIONS, not available from the menu.
def Handle_option_14(driver, user_inputs, output_lists):
    """Check/Update following statused of people you are following.
    
    This function checks all users that you are following to see whether they are following you or not.
    If you already have a following list on  disk, this will offer you to update the file, instead of doing everything from scratch.
    Note: this is a time-cosumming process. Use it responsibly and respectfully 
    """

    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.replace(microsecond=0).strftime(DATE_FORMAT)
    if user_inputs.number_of_users == -1:
        message = f'Get the following statuses of all users that {user_inputs.user_name} is following:'
    else:
        message = f'Get the following statuses of {user_inputs.number_of_users} users, starting from index {user_inputs.index_of_start_user + 1}:'
    printG(message)
    
    csv_file = ''
    # Provide option whether to use the last Followings list on disk or to start from scratch
    files = [f for f in glob.glob(output_lists.output_dir + f"**/{user_inputs.user_name}*followings*.csv")]
    files.sort(key=lambda x: os.path.getmtime(x))
    if len(files) > 0:
        print('    Existing Followings list on disk:')
        printY(f"{files[-1]}")
        sel = input("Using this file? (y/n) > ")
        # use the existing followings list
        if sel =='y':
            csv_file = files[-1]
        # redo the followings list:        
        else:
            print(f"    Getting {user_inputs.user_name}'s Followings list ...")
            #driver = Start_chrome_browser(headless_mode = HEADLESS_MODE) 
            output_lists.followings_list = Get_followings_list(driver, user_inputs, output_lists)
            #Close_chrome_browser(driver)
            # write result to csv
            if len(output_lists.followings_list) == 0:
                printR(f'    User {user_inputs.user_name} does not follow anyone or error on getting the followings list')
                return ''
            csv_file = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{len(output_lists.followings_list)}_followings_{date_string}.csv')
            if Write_users_list_to_csv(output_lists.followings_list, csv_file) == False:
                printR(f'    Error writing the output file\n:{csv_file}')
                return ''
    # do task
    #driver = Start_chrome_browser(headless_mode = HEADLESS_MODE) 
    Get_following_statuses(driver, user_inputs, output_lists, csv_file )
    #Close_chrome_browser(driver)
    html_file = CSV_to_HTML(csv_file, output_lists, use_local_thumbnails = USE_LOCAL_THUMBNAIL, 
                            ignore_columns = ['Avatar Href', 'Avatar Local','User Name', 'ID'])
    Show_html_result_file(html_file) 

    # print summary report
    time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
    print(f' The process took {time_duration} seconds') 
#---------------------------------------------------------------
def Handle_option_15(driver, user_inputs, output_lists, sort_column_header='No', ascending=True):
    """Like n photos of m users from a given csv files. 

    - The given csv file is supposed to have a header row, with at least one column named 'User Name'.
      All the csv files produced by this program, except the photo list file, satisfy this requirement and can be used.
    - There is an option to process part of the list, by specifying the start index and the number of users   
    - There is also option to sort a column in the csv file before processing 
    """
    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.replace(microsecond=0).strftime(DATE_FORMAT)
    printG("Like n photos of m users from a given csv files:")

    # do main task
    dframe = pd.read_csv(user_inputs.csv_file, encoding='utf-16')  
    # validate the given  csv file
    if len(list(dframe)) == 0 or not 'User Name' in list(dframe):
        printR(f'The given csv file is not valid. It should  have a header row with  at leat one column named "User Name":.\n\t{user_inputs.csv_file}')
        return

    print(f"    Like {user_inputs.number_of_photos_to_be_liked} photos from {user_inputs.number_of_users} users, starting from index {user_inputs.index_of_start_user} from the file:")
    printG({user_inputs.csv_file})    
    print(f'    There are {dframe.shape[1]} columns:')
    printG(list(dframe))
    sort_header = input('Enter the desired sort column >')
    if not sort_header:
        sort_header = "No" 
    sort_ascending = True
    ans = input('Sort descending ?(y/n) >')
    if ans == 'y':
        sort_ascending = False
    df = dframe.sort_values(sort_header, ascending = sort_ascending )   
    
    #driver = Start_chrome_browser(headless_mode = HEADLESS_MODE) 
    if not Logged_in(driver):
        if Login(driver, user_inputs) == False :
            #Close_chrome_browser(driver)
            return
    count = 0

    # if requesting all items:
    if user_inputs.index_of_start_user == -1:
        start_index = 0
        end_index = df.shape[0] -1
    else:
        # make sure the user's inputs stay within the size of the csv file 
        start_index = min(user_inputs.index_of_start_user, df.shape[0] -1)
        end_index   = min(user_inputs.index_of_start_user + user_inputs.number_of_users, df.shape[0] -1)

    for index, row in df.iloc[start_index:end_index].iterrows():
        user_inputs.target_user_name = row["User Name"]
        count += 1
    
        # process each user in dataframe
        try:
            print(f'    User #{count}: {row["Display Name"]}  at row {row["No"]}   ({row[sort_header]} likes):')
        except:
            print(f'    User #{count}: {row["User Name"]}:')

        Like_n_photos_from_user(driver, user_inputs.target_user_name, user_inputs.number_of_photos_to_be_liked, include_already_liked_photo_in_count=True, close_browser_on_error = False)

    #Close_chrome_browser(driver)
 
    # print summary report
    time_duration = (datetime.datetime.now().replace(microsecond=0) - time_start)
    print(f' The process took {time_duration} seconds') 
#---------------------------------------------------------------
def Save_avatar(url, path):
    """ Save the 500px user avatar to the given path on disk. 500px avatar file has this format "stock-photo-[user ID].jpg". 
        We will extracted it the file from the header, and use just the user id for filename. 
        The users who do not not provide an avatar have a default avatar, which we will save as well
        Existing file will be overwritten
        Return the file name
     
    This function is meant to be called repeatedly in the loop, so for better performance, we don't chech the existance of the given path
    We have to make sure the given path is valid prio to calling this. 
    """ 
    file_name = '' 
    try:
        r = requests.get(url, allow_redirects=True)
        time.sleep(random.randint(1, 5) / 10)         
        file_name =  r.headers.get('content-disposition').replace('filename=stock-photo-','')
    except:
        # default avatar if user does not have one: https://pacdn.500px.org/userpic.png
        file_name = url.split('/')[-1]

    full_file_name = os.path.join(path + "\\", file_name)
    #if not os.path.isfile(full_file_name):
    with open(full_file_name, 'wb+') as f:
        f.write(r.content)
    return file_name

#---------------------------------------------------------------
def Save_photo_thumbnail(url, path):
    """ Save the photo thumbnail to the given path on disk. 500px thumbnail files has this format "stock-photo-[photo ID].jpg". 
        We will extracted the filename from the header, and use just the photo id for filename. 
        Existing file will be overwritten
        Return the file name
     
    This function is meant to be called repeatedly in the loop, so for better performance, we don't chech the existance of the given path
    We have to make sure the given path is valid prio to calling this. 
    """ 
    file_name = '' 
    try:
        r = requests.get(url, allow_redirects=True)
        time.sleep(random.randint(1, 5) / 10)         
        file_name =  r.headers.get('content-disposition').replace('filename=stock-photo-','')
    except:
        printR(f'    Error getting photo thumbnail url: {url}')

    full_file_name = os.path.join(path + "\\", file_name)
    #if not os.path.isfile(full_file_name):
    with open(full_file_name, 'wb+') as f:
        f.write(r.content)
    return file_name

#---------------------------------------------------------------
def main():
    os.system('color')
    #driver = None

    driver = Start_chrome_browser(headless_mode = HEADLESS_MODE)
    user_inputs = Define_and_read_command_line_arguments()

    # declare a dictionary so that functions can be referred to from a string from "1" to "14"
    Functions_dictionary = {   
            "1" : Handle_option_1, 
            "2" : Handle_option_2, 
            "3" : Handle_option_3,
            "4" : Handle_option_4, 
            "5" : Handle_option_5, 
            "6" : Handle_option_6, 
            "7" : Handle_option_7, 
            "8" : Handle_option_8, 
            "9" : Handle_option_9, 
            "10": Handle_option_10, 
            "11": Handle_option_11,
            "12": Handle_option_12, 
            "13": Handle_option_13,  
            "14": Handle_option_14,
            "15": Handle_option_15}

    output_lists = Output_data()
    user_inputs = Define_and_read_command_line_arguments()
 
    if  user_inputs.use_command_line_args == False:
        Show_menu(user_inputs)  
   
    while user_inputs.choice != 'q':
        #restart for different user
        if user_inputs.choice == 'r': 
            user_inputs.Reset()
            output_lists.Reset()
            Close_chrome_browser(driver)
            driver = Start_chrome_browser(headless_mode = HEADLESS_MODE)
            user_inputs = Define_and_read_command_line_arguments()
            Show_menu(user_inputs, 'Restarted for a different user.')
            continue
        else:
        # add user to enter additional inputs according to the selected options
            if not user_inputs.use_command_line_args and int(user_inputs.choice) >= 5:
                if Get_additional_user_inputs(user_inputs) == False:
                    continue

            # dynamically call the function to perform the task 
            Functions_dictionary[user_inputs.choice](driver, user_inputs, output_lists)

        # after finishing a task, if we are in the command-line mode, we are done, since the specific task has finished 
        if  user_inputs.use_command_line_args:
            sys.exit()
             
        # if not, show the menu for another task selection  
        else:
            input("Press ENTER to continue")
            Show_menu(user_inputs)
            continue

    Close_chrome_browser(driver)
    sys.exit()

#---------------------------------------------------------------
if __name__== "__main__":
    main()

