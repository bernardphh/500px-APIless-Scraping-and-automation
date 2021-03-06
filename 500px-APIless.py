import common.apiless as apiless
import common.config as config
import common.utils as utils
import common.webtools as webtools
import common.database as db
import common.htmltools as htmltools
from common.config import LOG as logger
from common.utils import print_and_log, printB, printC, printG, printR, printY, printW

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains  
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import NoSuchElementException   
from selenium.common.exceptions import StaleElementReferenceException
from selenium.common.exceptions import ElementNotInteractableException
from selenium.common.exceptions import TimeoutException
import pandas as pd
from lxml import html
import glob, random, requests, sqlite3
import os, sys, time, datetime, re, math, json, argparse

from time import sleep
from os import listdir
from os.path import isfile, join
from dateutil.relativedelta import relativedelta
import multiprocessing as mp  
from threading import Thread
import queue

# a global variable for keeping track of loggin status between the tasks
logged_in = False
      
#---------------------------------------------------------------
def get_user_summary(driver, user_inputs, output_lists):
    """Get summary of a given user: number of likes, views, followers, following, photos, last upload date...
       If success, return statistics object and a blank message. If not return None and the error message

       Process:
       - Open user home page https://500px.com/[user_name]
       - Open the last uploaded photo to extract its uploaded date
       - Open the user About page https://500px.com/[user_name]/about
       - Extract the json part in the content, and obtain detailed data from it.
    """
    global logged_in
    print("    - Open user home page ...")

    success, message = webtools.open_user_home_page(driver, user_inputs.user_name)
    if not success:
        if message.find('Error reading') != -1:
            user_inputs.user_name,  user_inputs.db_path = '', ''
        return None, message

    # extract the date of the last upload
    time_out = 30
    last_upload_date = ''
    try:
        # wait for the photos container to be present
        container = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.ID, 'justifiedGrid')))
        items = webtools.check_and_get_all_elements_by_xpath(container, '*')
        if len(items) > 0:
            # logged in user has the first photo slot used for advertising "... Upgrade membership ..."
            first_ele = items[1] if logged_in and len(items) > 1 else items[0]
            last_photo_ele = webtools.check_and_get_ele_by_tag_name(first_ele, 'img')
            # open the last upload photo
            driver.execute_script("arguments[0].click();", last_photo_ele) 
            time.sleep(3)

    except Exception  as ex:
         logger.error(f'General exception: {ex}')
         printR(f'     Error opening the last photo. Ignoring the last upload date.')
    
    else:
         print("    - Getting the last upload date ...")
         uploaded_ele = webtools.check_and_get_ele_by_xpath (driver, "//span[contains(text(), 'Uploaded:')]")
         if uploaded_ele:
            last_upload_date = utils.convert_relative_datetime_string_to_absolute_date(uploaded_ele.text.replace('Uploaded: ', ''))

    


    # extract other profile info from user's About page
    driver.get(f'https://500px.com/{user_inputs.user_name}/about')     
    try:
        # wait for the content to be present
        WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.ID, 'content')))
    except TimeoutException:
        printR(f"Timed out {time_out}s while loading the user's About. Please try again later")

    hide_banners(driver)
 
    innerHTML = driver.execute_script("return document.body.innerHTML")  
    
    print("    - Getting user summary ...")
    # using lxml for html handling
    page = html.document_fromstring(innerHTML)

    # Affection note
    affection_note = webtools.get_element_attribute_by_ele_xpath(page, "//li[@class='affection']", 'title' )
    # Following note
    following_note = webtools.get_element_attribute_by_ele_xpath(page, "//li[@class='following']", 'title' )
    # Views count
    views_ele = webtools.check_and_get_ele_by_class_name(driver,'views' )
    if views_ele is not None:
        ele =  webtools.check_and_get_ele_by_tag_name(views_ele,'span')
        if ele is not None:
            views_count= ele.text

    # Location
    location = webtools.get_element_text_by_xpath(page,'//*[@id="content"]/div[1]/div[4]/ul/li[5]')
    if location == '':
        location = '<i>not specified'

    #using regex to extract from the javascript-rendered html the json part that holds user data 
    # Jul 26 2019: modification due to page structure changes: photos list is no longer included in userdata
    #   userdata = re.findall('"userdata":(.*),"viewer":', innerHtml)
    i = innerHTML.find('"userdata":') 
    j = innerHTML.find('</script>', i)
    userdata = innerHTML[i + 11 : j - 2]
    if len(userdata) == 0:
       return None, 'Error getting the user data'
    
    json_data = json.loads(userdata)

    regis_date = json_data['registration_date'][:10]
    try:
        registration_date = datetime.datetime.strptime(regis_date, "%Y-%m-%d").date().strftime("%b %d %Y")
    except:
        registration_date = regis_date

    active_int = json_data['active'] 
    if   active_int == 0 : user_status = 'Not Active'
    elif active_int == 1 : user_status = 'Active'
    elif active_int == 2 : user_status = 'Deleted by user'
    elif active_int == 3 : user_status = 'Banned'

    # write to file the userdata in json for debugging
    if config.DEBUG:
        jason_string = json.dumps(json_data, indent=2, sort_keys=True) 
        time_stamp = datetime.datetime.now().replace(microsecond=0).strftime("%Y_%m_%d__%H_%M_%S")
        utils.write_string_to_text_file(jason_string, os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_stats_json_{time_stamp}.txt'))

    stats = apiless.UserStats(json_data['fullname'], user_inputs.user_name, json_data['id'], location, 
                       affection_note, following_note, json_data['affection'], views_count, json_data['followers_count'], json_data['friends_count'], 
                       json_data['photos_count'], json_data['galleries_count'], registration_date, last_upload_date, user_status)
    return stats, ''

#---------------------------------------------------------------

#@utils.profile
def process_a_photo_element(driver, index, photos_count, photo_href, photo_thumbnail_href, user_name, user_password, thumbnails_list, thumbnails_dir):
    """Extract photo info from web element, return a photo object"""

    global logged_in

    # reset variables
    photo_id, title, photo_thumbnail_local = '0', '', ''
    photo_stats = apiless.PhotoStats()        

    # photo id
    photo_id  =  re.search('\/photo\/(\d+)', photo_href).group(1)

    # save the photo thumbnail to disk
    if config.USE_LOCAL_THUMBNAIL:
        photo_thumbnail_local = photo_id + '.jpg'
        if not photo_thumbnail_local in  thumbnails_list:
            #time.sleep(random.randint(5, 10) / 10)  
            photo_thumbnail_local = utils.save_photo_thumbnail(photo_thumbnail_href, thumbnails_dir )

    # open each photo page to get photo statistics
    id = ''
    order = index + 1      

    driver.get(photo_href)   
    time_out = 30
    try:  
        info_box = WebDriverWait(driver, time_out).until(EC.visibility_of_element_located((By.XPATH, '//*[@id="root"]/div[4]/div/div')) )
    except  TimeoutException:
        # log error, add the current photo with what are extracted so far, then go on with the next photo
        printR(f'   - Time out ({time_out}s) loading photo page.\n     Photo#{index + 1}, {title} will have incomplete info')
        return apiless.Photo(author_name = user_name, order = order, id = photo_id, title = title, thumbnail_href = photo_thumbnail_href, 
                             thumbnail_local = photo_thumbnail_local, stats = photo_stats ) 

    info = list(info_box.text.split('\n'))
    title          = info[0]
    upload_date    = [s for s in info if 'Uploaded:' in s][0].replace('Uploaded: ', '')
    photo_stats.upload_date = utils.convert_relative_datetime_string_to_absolute_date(upload_date, format = "%Y %m %d")

    # comments_count
    comments_count = [s for s in info if 'Comments' in s]
    if len(comments_count) > 0:
        comments_count = comments_count[0].replace('Comments', '')
        if comments_count.strip().isnumeric():
            photo_stats.comments_count = int(comments_count)
   
    # highest_pulse  
    highest_pulse  = info[info.index('Pulse') + 1] if 'Pulse' in info else '0.0'
    photo_stats.highest_pulse = float(highest_pulse)

    # views_count
    views_count = info[info.index('Impressions') + 1] if 'Impressions' in info else '0'
    photo_stats.views_count = utils.convert_string_num_to_int(views_count)

    # votes_count
    votes_count  = [s for s in info if 'people liked this photo' in s]
    if len(votes_count) > 0:
        votes_count = votes_count[0].replace('people liked this photo', '')
        photo_stats.votes_count = utils.convert_string_num_to_int(votes_count)
    
    # category
    index_category = info.index('Category:') if 'Category:' in info else -1
    index_featured = info.index('Featured in these Galleries') if 'Featured in these Galleries' in info else -1
    if index_category != -1 and index_featured != -1:        
        photo_stats.category = info[index_category + 1] 

        # string of tags
        tags = info[index_category + 2: index_featured]
        if 'View more' in tags:
            tags.pop(tags.index('View more'))
        tags.sort()
        photo_stats.tags = ",".join(tags)

    # featured galleries, count and string of galleries names
    galleries_count = 0
    galleries_string = ''    

    if logged_in and  'This photo has not been added to any Galleries' not in info:
        # find the View all text and click on that to load all featured galleries
        hrefs = []
        try:
            view_all_ele = info_box.find_elements_by_xpath("//*[contains(text(), 'View all')]")
        except StaleElementReferenceException:
            # DOM has changed. Reload it
            logger.info('StaleElementReferenceException on info_box element in process_a_photo_element function')
            info_box =  webtools.check_and_get_all_elements_by_xpath(driver, '//*[@id="root"]/div[4]/div/div')
            view_all_ele = info_box.find_elements_by_xpath("//*[contains(text(), 'View all')]")

        # featured galleries: case 1: there are galleries but not all of them are showing ( There exists a text 'View all')
        # find the text 'View all' and click on that to open the modal window that hosts the galleries, then get the container elemment
        if len(view_all_ele) > 0:
            driver.execute_script("arguments[0].click();", view_all_ele[0]) 
            time_out = 30
            try:
                container_ele = WebDriverWait(driver, time_out).until( EC.presence_of_element_located((By.CLASS_NAME, 'infinite-scroll-component')) )
            except  TimeoutException:
                printR(f'   Time out ({time_out}s! Error loading galleries.')
            else:
                # we use the tag img just to identify loading galleries and scroll into view the last item in order to load more
                img_eles = webtools.check_and_get_all_elements_by_tag_name(container_ele, 'img')
                # for now, we just scroll down 3 times to accept roughly 45 galleries
                # this is because 500px eventually gives bogus galleries, as we go toward the end of the phlist
                max_scrolldown = 3
                for _ in range(max_scrolldown):
                    img_eles[-1].location_once_scrolled_into_view
    
        # featured galleries: case 2: there are galleries and all are already in view. 
        # get the container element
        else:
            container_eles = webtools.check_and_get_all_elements_by_class_name(driver, 'slick-track') #slick-slide   parent: slick_list
            if len(container_eles) > 0:
                container_ele = container_eles[0]

        # now that we have the container for both cases 1 and 2, we grap all the 'a' tags 
        if container_ele :
            href_eles = webtools.check_and_get_all_elements_by_tag_name(container_ele, 'a')
        # then their href attributes
        for ele in href_eles:
            href = ele.get_attribute('href')
            if 'null' in href or 'galleries' not in href:
                continue
            if not href in hrefs:
                hrefs.append(href)
        # then remove the duplicates, and filter out unwanted hrefs, ie. not containing the text 'galleries'
        galleries = [] 
        [galleries.append(x) for x in hrefs if 'galleries' in x and x not in galleries]
        photo_stats.collections_count = len(galleries)
        galleries_string =  ",".join(galleries)

    return apiless.Photo(author_name = user_name, order = order, id = photo_id, title = title, href = photo_href, 
                        thumbnail_href = photo_thumbnail_href, thumbnail_local = photo_thumbnail_local, galleries = galleries_string, stats = photo_stats )  

#---------------------------------------------------------------
#@utils.profile
def get_not_logged_in_user_photos_list(driver, user_inputs, output_lists, photo_group_href):
    """ Return the list of public photos from a given user.
        This function is used when user does not loggin. The public photos are access via 500px.com/user_name   
        ( if the user was logged in, besides the public photos, we also access Unlisted, Limited-Access photos,
          These photos are under 500px/manage and these pages have different structures. The function in this case is get_managed_photos_list() )

    Process: 
    - Open user home page, scroll down until all photos are loaded
    - Extract photo data: no, id, photo title, href, thumbnail, views, likes, comments, galleries, highest pulse, rating, date, category, tags
    """

    photos_list = []
 
    success, message = webtools.open_user_home_page(driver, user_inputs.user_name)
    if not success:
        if message.find('Error reading') != -1:
            user_inputs.user_name,  user_inputs.db_path = '', ''
        return [], message
 
    # wait for the photos container to be present
    time_out = 30
    try:
        container = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.ID, 'justifiedGrid')))
    except TimeoutException:
        printR(f'Timed out {time_out}s while loading photos container. Please try again later')
        return [], ''

    # get photos count
    photos_count = 0
    try:
        photos_count_ele = WebDriverWait(driver, time_out).until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Photos ')]")))
        texts = photos_count_ele.text.split(' ')
        if len(texts) > 1:
            count = texts[1].strip().replace(",", "").replace(".", "")
            if count.isnumeric():
                photos_count = int(count)
    except TimeoutException:
        printR(f'Timed out {time_out}s while loading photos. Please try again later')
        return

    # get the inially loaded photos: first-level childs of the container
    # scrolling down to load all, if needed
    items = webtools.check_and_get_all_elements_by_xpath(container, '*')
    if len(items) < photos_count:               
        img_eles = webtools.scroll_to_end_by_tag_name_within_element(driver, container, 'img', photos_count, time_out = 30)
    else:
        img_eles = webtools.check_and_get_all_elements_by_tag_name(container, 'img')
    
    # list of thumbnail href of loaded photos 
    photos_thumbnail_href = [ele.get_attribute('src') for ele in img_eles]

    imgs_ele_parents =  [webtools.check_and_get_ele_by_xpath(ele, '..') for ele in img_eles]   
    photos_href =  [ele.get_attribute('href') for ele in imgs_ele_parents]

    for i in range(photos_count): 
        utils.update_progress((i + 1) / (photos_count), f'    - Extracting  {i + 1}/{photos_count} photos:')
        this_photo = process_a_photo_element(driver, i, photos_count, photos_href[i], photos_thumbnail_href[i], 
                                          user_inputs.user_name, user_inputs.password, output_lists.thumbnails_list, output_lists.thumbnails_dir)
        photos_list.append(this_photo)

    return  photos_list, ''

#---------------------------------------------------------------
#@utils.profile
def get_managed_photos_list(driver, user_inputs, output_lists, photo_group_href):
    """Return the list of a given photos group from a given user.
       User is expected to be logged in for the Unlisted and Limited-access groups to be available.
       All photos, including the public photos, are accessed via the 500px.com/manage/ 

    Process:  
    - Open given photo group page, scroll down until all photos are loaded
    - Extract photo data: no, id, photo title, href, thumbnail, views, likes, comments, galleries, highest pulse, rating, date, category, tags
    """

    photos_list = []
    driver.get(photo_group_href)
    time_out = 30
    try:
        photo_list_ele = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.CLASS_NAME, 'photos_list')))
        #photo_list_ele = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.ID, 'justifiedGrid')))
    except TimeoutException:
        printR(f'Timed out {time_out}s while loading photos container. Please try again later')
        return [], ''
    
    # We request 3 specific photo groups: public, unlisted and limited access. 
    # Some users may have only one or two groups. A request to a missing group href will be automatically switch to the main page :500px.com/manage.
    # When it happens, we just silently ignore the non-existing group  
    if driver.current_url.split('/')[-1] != photo_group_href.split('/')[-1]:
        return [], ''

    time_out= 30

    # get photos count
    photos_count = 0
    try:
        total_count_ele = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.CLASS_NAME, 'total_count')))
        total_count = total_count_ele.text.split(' ')[0].strip()
        if total_count.isnumeric():
            photos_count = int(total_count)
    except TimeoutException:
        printR(f'Timed out {time_out}s while loading photos. Please try again later')
        return
    webtools.scroll_to_end_by_class_name(driver, 'photo_item', photos_count)
   
    # get container element from it we can extract all photo thumbnails and photo links
    try:
        photo_list_ele = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.CLASS_NAME, 'photos_list')))
    except TimeoutException:
        printR(f'Timed out {time_out}s while loading photos container. Please try again later')
        return

    img_eles = webtools.check_and_get_all_elements_by_tag_name(photo_list_ele, 'img')
    a_eles = webtools.check_and_get_all_elements_by_tag_name(photo_list_ele, 'a')
    photos_thumbnail_href = [ele.get_attribute('src') for ele in img_eles]
    photos_href =  [ele.get_attribute('href') for ele in a_eles]
    if False: #DEBUG:
        assert len(photos_thumbnail_href) == photos_count and len(photos_href) == photos_count 

    for i in range(photos_count): 
        utils.update_progress((i + 1) / (photos_count), f'    - Extracting  {i + 1}/{photos_count} photos:')
        this_photo = process_a_photo_element(driver, i, photos_count, photos_href[i], photos_thumbnail_href[i], 
                                          user_inputs.user_name, user_inputs.password, output_lists.thumbnails_list, output_lists.thumbnails_dir)
        photos_list.append(this_photo)

    return  photos_list, ''

#---------------------------------------------------------------
def get_followers_list(driver, user_inputs, output_lists):
    """Get the list of users who follow me. Info for each item in the list are: 
       No, Avatar Href, Avatar Local, Display Name, User Name, ID, Followers, Relationship
       If logged in, we can extract my following status to each of my followers  ( whether or not I'm alse following my follower)  
    Process:
    - Open the user home page, locate the text "followers" and click on it to open the modal windonw that hosts the followers list
    - Scroll to the end for all items to be loaded
    - Make sure the document js is running for all the data to load in the page body
    - Extract info and put in a list. 
    - Return the list
    """

    followers_list = []
    followers_count = 0
    number_of_followers = ''
    if driver.current_url != 'https://500px.com/' + user_inputs.user_name:
        success, message = webtools.open_user_home_page(driver, user_inputs.user_name)
        if not success:
            printR('   - ' + message)
            if message.find('Error reading') != -1:
                user_inputs.user_name,  user_inputs.db_path = '', ''
            return followers_list

    hide_banners(driver)
    # wait for the Follower text icon to be available and click it to open that the modal window that host the followers list 
    time_out = 30
    try:  
        followers_text_ele = WebDriverWait(driver, time_out).until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Follower')]")))
        #followers_text_ele.click()
        driver.execute_script("arguments[0].click();", followers_text_ele) 
        time.sleep(1)
    except  TimeoutException:
        printR(f'   - Time out ({time_out}s) loading followers list')   
        return []
    except Exception as e:
        logger.info(f'Exception: {e}')
        printY('   Failed to open the Followers list. Please try again.')
        return []

    # extract number of followers on the modal window                
    try:  
        #follower_headline_ele = WebDriverWait(driver, time_out).until(EC.visibility_of_element_located((By.XPATH, "//*[contains(text(), 'Followers ')]")))
        follower_headline_ele = webtools.check_and_get_ele_by_xpath(driver, "//*[contains(text(), 'Followers ')]")
        # remove thousand-separator character, if existed
        followers_count = int(follower_headline_ele.text.replace(",", "").replace(".", "").replace('Followers', '').strip())
    except  TimeoutException:
        printR(f'   - Error while getting the number off followers. Please try again.')
        return []
    except:
        printR(f'   Error converting followers count to int: {followers_count} Please try again.')
        return []
    
    printG(f'   {user_inputs.user_name} has {str(followers_count)} follower(s)' )

    # get the container that hosts all users:  a div of class: infinite-scroll-component 
    container = webtools.check_and_get_ele_by_xpath(driver, '//*[@id="followers-modal"]/div/div/div')
    if not container:
        printR('Error getting the Followers list. Please try again')
        return []

    # scroll down to load all users
    webtools.scroll_to_end_by_tag_name_within_element(driver, container, 'img', followers_count, time_out = 10)

    # now that we have all followers loaded, start extracting the info
    # get all direct (immediate) children under the container: all div tags of class: StyledLayout__Box-xxxxxxxxxxxxxx
    if container:
        items = webtools.check_and_get_all_elements_by_xpath(container, '*')

    for i, item in enumerate(items):

        utils.update_progress( (i + 1) / (len(items) ), f'    - Extracting data {i + 1}/{len(items)}:')
        user_name, display_name, follower_page_link, following_status, avatar_href, avatar_local = ('' for i in range(6))
        count = ' '
        user_id = '0'
        
        # get display name and followers count
        texts = item.text.split('\n')
        if len(texts) > 1: 
            display_name = texts[0] 
            number_of_followers =  texts[1].replace(' Followers', '').replace(' Follower', '') 
        # as observed, there exists an extra item at the end. It is not an user element, but got counted as one (bug)
        # we catch it here then simply ignore it.
        else:
            logger.info( f'   Ignore element: Follower #{i+1}: {texts}')
            continue
 
        try:
            # get user name, avatar href, avatar local and user id, if user does not use default avatar
            a_ele = item.find_element_by_xpath('./div[1]/div/a')
            if a_ele:
                follower_page_link = a_ele.get_attribute('href')
                user_name = follower_page_link.split('/')[-1]
                img_ele = webtools.check_and_get_ele_by_tag_name(item, 'img') 
                if img_ele:
                    avatar_href = img_ele.get_attribute('src')
                    user_id, avatar_local = utils.handle_local_avatar(avatar_href, save_to_disk = config.USE_LOCAL_THUMBNAIL, dir = config.OUTPUT_PATH)

        except:  # log any errors during the process but do not stop 
            printR(f'\n   Error on getting user # {i + 1}: name: {display_name}, user name: {user_name}. Some info may be missing!')

        followers_list.append(apiless.User(order = str(i+1), avatar_href = avatar_href, avatar_local = avatar_local, display_name= display_name, 
                                   user_name = user_name, id = user_id, number_of_followers = number_of_followers, following_status = following_status))
    return followers_list 

#---------------------------------------------------------------
def does_this_user_follow_me(driver, user_inputs):
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
        success, message = webtools.open_user_home_page(driver, user_inputs.target_user_name)
        if not success:
            if message.find('Error reading') != -1:
                user_inputs.target_user_name = ''
            return False, message
  
    hide_banners(driver)     

    # click on the Following text to open the modal window
    time_out = 30
    ele = None
    try:  
        following_text_ele = WebDriverWait(driver, time_out).until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Following')]")))
        driver.execute_script("arguments[0].click();", following_text_ele) 
        time.sleep(2)
    except  TimeoutException:
        return False, f'   - Time out ({time_out}s) loading Following list. Please retry'    
    # extract number of following on the modal window                 
    try:  
        #following_text_ele = WebDriverWait(driver, time_out).until(EC.visibility_of_element_located((By.XPATH, "//*[contains(text(), 'Following ')]")))
        following_text_ele = webtools.check_and_get_ele_by_xpath(driver, "//*[contains(text(), 'Following ')]")
        following_count = int(following_text_ele.text.replace(",", "").replace(".", "").replace('Following', '').strip())
    except  TimeoutException:
        return False, f'   - Error while getting the number of following. Please try again.'
    except:
        return False, f'   Error converting followers count to int: {following_text_ele.text}Please try again.'
   
    printG(f'   {user_inputs.target_user_name} is following {str(following_count)} user(s)' )
  
    # get the container that hosts all users:  a div of class: infinite-scroll-component 
    container = webtools.check_and_get_ele_by_xpath(driver, '//*[@id="following-modal"]/div/div/div')
    if not container:
        return False, 'Error getting the Following list'

    # start the progress bar
    utils.update_progress(0, '    - Processing loaded data:')
    iteration_num = math.floor(following_count / config.USERS_PER_LOAD) + 1    

    users_done = 0
    current_index = 0   # the index of the photo in the loaded photos list. We dynamically scroll down the page to load more photos as we go, so ...
                        # ... more photos are appended at the end of the list. We use this current_index to keep track where we were after a list update 
    
  
    img_eles = webtools.check_and_get_all_elements_by_tag_name(container, 'img')
    imgs_ele_parents =  [webtools.check_and_get_ele_by_xpath(ele, '..') for ele in img_eles]   
    photos_href =  [ele.get_attribute('href') for ele in imgs_ele_parents]
    following_names = [photo_href.split('/')[-1] for photo_href in photos_href] 
    loaded_users_count = len(following_names)

    while users_done < following_count: 
        # check if we have processed all loaded users, then we have to load more  
        if current_index >= loaded_users_count - 1: 
            prev_loaded_users = loaded_users_count
            the_last_in_list = img_eles[-1]
            the_last_in_list.location_once_scrolled_into_view 
            time.sleep(2)
  
            # update list with more users
            img_eles = webtools.check_and_get_all_elements_by_tag_name(container, 'img')
            imgs_ele_parents =  [webtools.check_and_get_ele_by_xpath(ele, '..') for ele in img_eles]   
            photos_href =  [ele.get_attribute('href') for ele in imgs_ele_parents]
            following_names = [photo_href.split('/')[-1] for photo_href in photos_href] 
            loaded_users_count = len(following_names)
 
            # stop when no more users are loaded
            if loaded_users_count == prev_loaded_users:
                # there is discrepancy between the count of following users and the actual count (500px's buggy extra item at the end of the list)
                if loaded_users_count < following_count:
                    printR( f'\n      Only {loaded_users_count}/{following_count} users are available')
                break;

        utils.update_progress(current_index / following_count, f'    - Processing loaded data {current_index}/{following_count}:')  

        if user_inputs.user_name in following_names[current_index:]:
            found_index = following_names.index(user_inputs.user_name)
            utils.update_progress(1, f'    - Processing loaded data {found_index}/{following_count}:')
            return True, f'Following you ({found_index}/{following_count})'

        current_index = loaded_users_count -1
        users_done = loaded_users_count
    return False, "Not following you"

#---------------------------------------------------------------
# This is a time-consuming process for users that have thousands of following user. This option is taken off from the main menu. 
# I'm evaluating the multiprocessing approach, on processing the already loaded data, not on multiple requests to the server.Stay tuned. For now I have a limit on the request number.
def get_following_statuses(driver, user_inputs, output_lists, csv_file):
    """ Get the following statuses of the users that you are following, with the option to specify the range of user in the following list.
   
    - start_user_index is 1-based and will be converted to 0-based
    - number_of_users : this is a lengthy process, so we provide this option to limit the number of users we will process. passing -1 to ignore this limit
    """

    # do main task
    df = pd.read_csv(csv_file, encoding='utf-16') #, usecols=["User Name"])     
    # a trick to force column Relationship content as string instead of the default float      
    df.Relationship = df.Relationship.fillna(value="")             
    # make sure the user's inputs stay in range with the size of the following list
    user_inputs.index_of_start_user = min(user_inputs.index_of_start_user, df.shape[0] -1)
    print('    Updating the following statuses on')
    printY(f'    {csv_file}', write_log=False)
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
        result, message = does_this_user_follow_me(driver, user_inputs)
        if result == True:
            printG('   - ' + message)
            # update the status column in the dataframe with following status
            df.at[index, 'Relationship'] = message 
        else:
            printR('   - ' + message) if 'User name not found' in message else printY('   - ' + message)
            continue
    try:
        # write back dataframe to csv file
        df.to_csv(csv_file, encoding='utf-16', index = False)
    except: 
        printR(f'   Error writing file {os.path.abspath(csv_file)}.\nMake sure the file is not in use. Then type r for retry >')
        retry = input()
        if retry == 'r': 
            df.to_csv(csv_file, encoding='utf-16', index = False)
        else:
            printR('   Error writing file' + os.path.abspath(csv_file))

#---------------------------------------------------------------
def get_followings_list(driver, user_inputs, output_lists):
    """Get the list of users who I'm  following. Info for each item in the list are: 
       No, Avatar Href, Avatar Local, Display Name, User Name, ID, Followers, Relationship

    PROCESS:
    - Open the user home page, locate the text "followings" and click on it to open the modal windonw that hosts followers list
    - Scroll to the end for all items to be loaded
    - Make sure the document js is completed for all the data to load in the page body
    - Extract info and put in a list. 
    - Return the list
    """
    followings_list = []
    following_count = 0
    if driver.current_url != 'https://500px.com/' + user_inputs.user_name:
        success, message = webtools.open_user_home_page(driver, user_inputs.user_name)
        if not success:
            printR('   - ' + message)
            if message.find('Error reading') != -1:
                user_inputs.user_name,  user_inputs.db_path = '', ''
            return followings_list

    hide_banners(driver)                  
                                          
    # wait for the Following text icon to be available and click pn it to open that the modal window that host the followings list 
    time_out = 30
    try:  
        following_text_ele = WebDriverWait(driver, time_out).until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Following')]")))
        driver.execute_script("arguments[0].click();", following_text_ele) 
        time.sleep(1)
    except  TimeoutException:
        printR(f'   - Time out ({time_out}s) loading Following list')   
        return []
    except Exception as e:
        logger.info(f'Exception: {e}')
        printY('   Failed to open the Following list. Please try again.')
        return []

    # extract number of followers on the modal window                 
    try:  
        following_text_ele = WebDriverWait(driver, time_out).until(EC.visibility_of_element_located((By.XPATH, "//*[contains(text(), 'Following ')]")))
    except  TimeoutException:
        printR(f'   - Error while getting the number of following')
        return []

    try:
        following_count = int(following_text_ele.text.replace(",", "").replace(".", "").replace('Following', '').strip())

    except:
        printR(f'   Error converting following users count to int: {following_text_ele.text}')
    else:
        printG(f'   {user_inputs.user_name} is following {str(following_count)} user(s)' )

   # get the container that hosts all users:  a div of class: infinite-scroll-component 
    container = webtools.check_and_get_ele_by_xpath(driver, '//*[@id="following-modal"]/div/div/div')
    if not container:
        printR('Error getting the Following list. Please try again')
        return []

   # scroll down to load all users
    webtools.scroll_to_end_by_tag_name_within_element(driver, container, 'img', following_count, time_out = 20)

    # now that we have all followers loaded, start extracting info
    # get all direct (immediate) children under the container: all div tags of class: StyledLayout__Box-xxxxxxxxxxxxxx
    if container:
        items = webtools.check_and_get_all_elements_by_xpath(container, '*')

    for i, item in enumerate(items):
        if i > 0:
            utils.update_progress( (i + 1) / (len(items) - 1), f'    - Extracting data {i + 1}/{len(items)}:')

        user_name, display_name, following_page_link, following_status, avatar_href, avatar_local = ('' for i in range(6))
        count = ' '
        user_id = '0'

       # get display name and following count
        texts = item.text.split('\n')
        if len(texts) > 1: 
            display_name = texts[0] 
            number_of_followers =  texts[1].replace(' Followers', '').replace(' Follower', '') 
        # as observed, there may exist an extra item at the end. It is not a user element, but got counted as one (bug)
        # we log it then simply ignore it.
        else:
            logger.info( f'   Following user #{i+1}: {texts}')
            continue

        try:
            # get user name, avatar href, avatar local and user id, if user does not use default avatar
            a_ele = item.find_element_by_xpath('./div[1]/div/a')
            if a_ele:
                following_page_link = a_ele.get_attribute('href')
                user_name = following_page_link.split('/')[-1]
                img_ele = webtools.check_and_get_ele_by_tag_name(item, 'img') 
                if img_ele:
                    avatar_href = img_ele.get_attribute('src')
                    user_id, avatar_local = utils.handle_local_avatar(avatar_href, save_to_disk = config.USE_LOCAL_THUMBNAIL, dir = config.OUTPUT_PATH)

        except:  # log any errors during the process but do not stop 
            printR(f'\n   Error on getting user # {i + 1}: name: {display_name}, user name: {user_name}. Some info may be missing!')

        followings_list.append(apiless.User(order = str(i+1), avatar_href = avatar_href, avatar_local = avatar_local, display_name= display_name, 
                                   user_name = user_name, id = user_id, number_of_followers = number_of_followers, following_status = following_status))
    return followings_list 

#---------------------------------------------------------------
def process_notification_element(notification_element, output_lists):
    """Process one notification item. Return a notification object of the following detail:
    No, Avatar Href, Avatar Local, Display Name, User Name, ID, Content, Photo Thumbnail Href, Photo Thumbnail Local, Photo Title, Time Stamp, Relationship, Photo Link
    """
    #if not notification_element or not output_lists:
    #    return

    (user_name, content, photo_link, display_name, photo_title, status, avatar_href, avatar_local, 
    photo_thumbnail_href, photo_thumbnail_local, abs_timestamp ) = ('' for i in range(11))
    user_id, photo_id=  '0', '0'

    notif_text = notification_element.text
    notif_text_list = notif_text.split('\n')
    
    # notification type, following status
    if   'Quest'     in notif_text: return None
    elif 'liked'     in notif_text: content = 'liked'
    elif 'added'     in notif_text: content = 'added to gallery'
    elif 'commented' in notif_text: content = 'commented'
    elif 'followed'  in notif_text: 
        content = 'followed'
        status  = 'Following' if 'Following' in notif_text else 'Not Follow'
        photo_link = ' '
    else: return None  #ignore the notification if the content cannot be identified

    # we convert the relative time(e.g "4 hours ago") to absolute time (e.g. 2020-03-08. 10:30:12AM)
    # so that we can put the notifications into a database without duplication, regardless of when we extracted them
    if len(notif_text_list) >=2: 
        abs_timestamp = utils.convert_relative_datetime_string_to_absolute_date(notif_text_list[1], format = "%Y %m %d")

    try:
        # get user_name, display_name
        actor = webtools.check_and_get_ele_by_class_name(notification_element, 'notification_item__actor') 
        if actor is None:
            return None
        display_name = actor.text
        user_name = actor.get_attribute('href').replace('https://500px.com/', '')

        # get user avatar, user id   
        avatar_ele = webtools.check_and_get_ele_by_class_name(notification_element, 'notification_item__avatar_img')             
        #time.sleep(random.randint(5, 10) / 10)  

        if avatar_ele is None:
            return None
        avatar_href = avatar_ele.get_attribute('src')
        user_id, avatar_local = utils.handle_local_avatar(avatar_href, save_to_disk = config.USE_LOCAL_THUMBNAIL, dir = config.OUTPUT_PATH)

        # photo title, photo link
        photo_ele = webtools.check_and_get_ele_by_class_name(notification_element, 'notification_item__photo_link')
        if photo_ele:  
            photo_title = photo_ele.text
            photo_link = photo_ele.get_attribute('href') 

        # get photo thumbnail
        photo_thumb_ele = webtools.check_and_get_ele_by_class_name(notification_element, 'notification_item__photo_img') 
        #time.sleep(random.randint(5, 10) / 10)
        if photo_thumb_ele is not None:
            photo_thumbnail_href = photo_thumb_ele.get_attribute('src')
            # save the photo thumbnail to disk
            if config.USE_LOCAL_THUMBNAIL:
                photo_thumbnail_local = utils.save_photo_thumbnail(photo_thumbnail_href, output_lists.thumbnails_dir )
                if photo_thumbnail_local:
                    photo_id = os.path.splitext(photo_thumbnail_local)[0]

    except:  # log any errors during the process but do not stop 
        printR(f'   Error on getting notification: actor: {display_name}, photo: {photo_title}.\nSome info may be missing!')

    # creating and return the notification object
    the_actor = apiless.User(avatar_href = avatar_href, avatar_local = avatar_local, display_name = display_name, user_name = user_name, id = user_id)
    the_photo = apiless.Photo(thumbnail_href = photo_thumbnail_href, thumbnail_local = photo_thumbnail_local, id = photo_id, href = photo_link, title = photo_title)

    return apiless.Notification(order = 0, actor = the_actor, the_photo = the_photo, content = content, timestamp = abs_timestamp,  status = status)

#---------------------------------------------------------------
#@utils.profile
def get_notification_list(driver, user_inputs, output_lists, get_user_names_only = False):
    """Get n last notification items (excluding Photo Quests). Return 2 lists, notifications list and a list of unique users from it
    
    A notification item contains full_name, user name, the content of the notification, title of the photo in question, the time stamp and the following status
    A unique user is comma separated string containing display name and user name
    If GET_USER_NAMES_ONLY=False (default) return notifications list and [] else,  return [] and the unique list
    PROCESS:
    - expecting the user was logged in, and the notification page is the active page
    - scroll down until all the required number of notifications are loaded
    - extract and return info according to the given argument GET_USER_NAMES_ONLY
    """

    unique_notificators, notifications_list, simplified_list = [], [], []

    # Feb 19 2020: we now can get the notifications from a certain index
    start_index = user_inputs.index_of_start_notification
    request_number = user_inputs.number_of_notifications
    length_needed = start_index + request_number

    #scroll down until all the required number of notifications are loaded, excluding Photo Quest notification
    webtools.scroll_down_active_page(driver,
                                     class_name_to_check = 'notification_item__photo_link', 
                                     number_requested = length_needed, 
                                     message = '    - Scrolling down for more notifications:' )    

    # get the info now that all we got all the available notifications
    items = driver.find_elements_by_class_name('notification_item')  
    
    notifications_list =[]
    unique_names = []
    names_pair = ''

    for i, item in enumerate(items[start_index:]):
        count_sofar = len(unique_names) if get_user_names_only else len(notifications_list)    
        if count_sofar >= request_number:
            break

        if get_user_names_only:
            actor = webtools.check_and_get_ele_by_class_name(item, 'notification_item__actor') 
            if actor:
                display_name = actor.text
                user_name = actor.get_attribute('href').replace('https://500px.com/', '')
                names_pair = f'{display_name},{user_name}'
                                  
                if not 'quests/' in user_name and not names_pair in unique_names:
                    unique_names.append(names_pair)
            continue

        else:
            new_notification = process_notification_element(item, output_lists)        
            if new_notification is not None:
                count_sofar += 1
                new_notification.order = len(notifications_list) + 1 + start_index
                notifications_list.append(new_notification)
                # advance the progress bar
                utils.update_progress(count_sofar/request_number, f'    - Extracted data {count_sofar}/{request_number}') 
             
    if len(notifications_list) == 0  and ( get_user_names_only and len(unique_names) == 0): 
        printG(f'   User {user_inputs.user_name} has no notification')
        return [], []

    if get_user_names_only:
        return [], unique_names
    else:
        return notifications_list, []
#---------------------------------------------------------------
def get_like_actioners_list(driver, user_inputs, output_lists, get_name_only = True):
    """Get the list of users who liked a given photo. If get_name_only=True, only extract user_name and display name, else get all other info.
       Return the list and a dictionary containing suggested file name, photo title and the like count

    PROCESS:
    - Expecting the active page in the browser is the given photo page
    - Run the document js to render the page body
    - Extract photo title and photographer name
    - Locate the like count number then click on it to open the modal window hosting the list of actioner user
    - Scroll down to the end and extract relevant info, put all to a list and return it
    """
    global logged_in
    actioners_list = []
    date_string = datetime.datetime.now().replace(microsecond=0).strftime(config.DATE_FORMAT)
    description_dict = {}
    time_out = 30
    try:  
        info_box = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.XPATH, '//*[@id="root"]/div[4]/div/div')) )
    except  TimeoutException:
        printR(f'   Time out ({time_out}s)! Please try again')
        return [], {}
  
    info = list(info_box.text.split('\n'))
    photo_title          = info[0]
    printG(f'     Photo title: {photo_title}')

    photographer_name  = info[info.index('by') + 1] if 'by' in info else ''
    printG(f'     Photogapher: {photographer_name}')

    likes_count  = [s for s in info if 'people liked this photo' in s]
    if len(likes_count) > 0:
        likes_count = likes_count[0].replace('people liked this photo', '')
        likes_count = utils.convert_string_num_to_int(likes_count)
        printG(f"     This photo has {likes_count} likes")

   # wait for the like-count-button to be available and click on it to open that the modal window that host the followings list 
    try:  
        photo_likes_count_ele = WebDriverWait(driver, time_out).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="root"]/div[4]/div/div/div[1]/div/div[3]/div[4]/span')))
        photo_likes_count_ele.click()
        time.sleep(1)
    except  TimeoutException:
        printR(f'   Time out ({time_out}s!) Please try again')
        return [], {}

    #get a container element containing all actors. 
    container = None
    try:
        container =  WebDriverWait(driver, time_out).until( EC.presence_of_element_located((By.CLASS_NAME, 'ant-modal-body')) )
        #container =  WebDriverWait(driver, time_out).until( EC.presence_of_element_located((By.CLASS_NAME, 'infinite-scroll-component ')) )
    except  TimeoutException:
        printR(f'   Time out ({time_out}s! Not all elements are loaded. You may try again later.')
        return [], {}
 
    # make a meaningful output file name
    like_actioners_file_name = os.path.join(output_lists.output_dir, \
        f"{user_inputs.user_name}_{likes_count}_{apiless.CSV_type.like_actors.name}_{photo_title.replace(' ', '-')}_{date_string}.csv")

    #scrolling down until all the actors are loaded
    img_eles = webtools.scroll_to_end_by_tag_name_within_element(driver, container, 'img', likes_count)
      
    if not user_inputs.password:
        print_and_log(f'      User {user_inputs.user_name} is not logged in, the following status will be "Unknown"')
  
    # create actors list
    actors_count = len(img_eles )
    info_list = container.text.split('\n')
    display_names = info_list[0::3]
    followers_counts = info_list[1::3]
    following_statuses = info_list[2::3]
    if False: #DEBUG:
        assert len(display_names) == actors_count and len(followers_counts) == actors_count and len(following_statuses) == actors_count

    following_statuses = [s.replace('Follow', 'Not Follow') if s == 'Follow' else s for s in following_statuses]
    followers_counts = [s.replace('Followers', '').strip() for s in followers_counts]

    for i, img in enumerate(img_eles):
        utils.update_progress(i / (actors_count - 1), f'    - Extracting data {i+1}/{actors_count}:')
        display_name, user_name, followers_count, following_status = ('' for i in range(4))
        avatar_href, avatar_local, user_id = '', ' ', '0'
        try: 
            display_name = display_names[i]
            img_ele_parent =  webtools.check_and_get_ele_by_xpath(img, '..')
            if img_ele_parent is None:
                continue
            user_name = img_ele_parent.get_attribute('href').replace('https://500px.com/','')
            if get_name_only:
                actioners_list.append(apiless.User(display_name = display_name, user_name = user_name))
                continue
            
            # get more details on each user
            avatar_href= img.get_attribute('src')      
            user_id, avatar_local = utils.handle_local_avatar(avatar_href, save_to_disk = config.USE_LOCAL_THUMBNAIL, dir = config.OUTPUT_PATH)
 
            followers_count = followers_counts[i]
            
            # get following status
            following_status =  'Unknown' if not logged_in else following_statuses[i]

        except:  # log any errors during the process but do not stop 
            printR(f'\n   Error on getting user # {i + 1}: name: {display_name}, user name: {user_name}.Some info may be missing!')

        actioners_list.append(apiless.User(order = str(i+1), avatar_href = avatar_href, avatar_local = avatar_local, display_name = display_name, 
                                    user_name = user_name, id = user_id, number_of_followers = str(followers_count), following_status = following_status) )  
        description_dict = {'Data file': like_actioners_file_name, 'Title': f'{actors_count} users liked photo {photo_title}'}
    return actioners_list, description_dict

#---------------------------------------------------------------
def like_n_photos_from_user(driver, target_user_name, number_of_photos_to_be_liked, include_already_liked_photo_in_count = True, close_browser_on_error = True):
    """Like n photo of a given user, starting from the top. Return False and error message if error occured, True and blank string otherwise

    If the INCLUDE_ALREADY_LIKED_PHOTO is true (default), the already-liked photo will be counted as done by the auto-like process
    for example, if you need to auto-like 3 photos from a user, but two photos in the first three photos are already liked, 
    then you only need to do one
    If the INCLUDE_ALREADY_LIKED_PHOTO_in_count is false, the process will auto-like the exact number requested
    the argument CLOSE_BROWSER_ON_ERROR needs to be false if this function is called in a loop: if errors occur, we want to process the next item
    PROCESS:
    - Open the user home page
    - Force document js to run to fill the visible body
    - Locate the first photo, check  it whether is already-liked, if yes, go the next photo, it no, click on the like icon to like the photo
    - Continue until the asking number of photos is reached. 
    - When we have processed all the loaded photos but the required number is not reached yet, 
      scroll down once to load more photos ( currently 500px loads 20 photos at a time) and repeat the steps until done
      """

    success, message = webtools.open_user_home_page(driver, target_user_name)
    if not success:
        printR(f'     {message}')
        return False, message
    time.sleep(2)

    time_out = 30
    try:
        container = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.ID, 'justifiedGrid')))
    except TimeoutException:
        message = f'Timed out {time_out}s while loading photos container. Please try again later'
        printR(f'     {message}')
        return False, message

    # loaded direct children of container, which are photos elements
    like_buttons, like_statuses = [], []
    childs = webtools.check_and_get_all_elements_by_xpath(container, '*')
    photos = [child for child in childs if child.get_attribute('id') !=  '']
    loaded_photos_count = len(photos)

    # scroll down, if needed, until the number of loaded photos reached the request amount
    time_out_countdown = 5
    while time_out_countdown > 0 and loaded_photos_count < number_of_photos_to_be_liked:
        childs[-1].location_once_scrolled_into_view
        time.sleep(1)
        childs = webtools.check_and_get_all_elements_by_xpath(container, '*')
        photos = [child for child in childs if child.get_attribute('id') !=  '']
        loaded_photos_count = len(photos)
        time_out_countdown -= 1

    if loaded_photos_count > 0:
        like_buttons =  [webtools.check_and_get_ele_by_xpath(photo, './/div[@role="button"]') for photo in photos]   
        # the parent of like button element has an attribute that shows whether the photo has been liked or not
        try:
            like_statuses =  [webtools.check_and_get_ele_by_xpath(like_button, '..').get_attribute('aria-label') for like_button in like_buttons]
        except Exception as e:
            logger.info(f'Exception: {e}')
            message = 'Error locating the like button. Ignore this user'
            printR(message)
            return False, message

    hide_banners(driver)        
    
    time.sleep(random.randint(10, 15) / 10)   
    if loaded_photos_count == 0:
        printY('   User has no photos')
    done_count = 0

    for i, like_button in enumerate(like_buttons):
        like_button.location_once_scrolled_into_view
        # skip already-liked photo. Count it as done if requested so
        if done_count < number_of_photos_to_be_liked and 'Unlike' not in like_statuses[i]: 
            if include_already_liked_photo_in_count == True:
                done_count = done_count + 1          
            printY(f'    - Liked #{str(done_count):3} Photo { str(i+1):2} - already liked')
            continue        

        # check limit
        if done_count >= number_of_photos_to_be_liked:  
            break
        if not config.HEADLESS_MODE:
            webtools.hover_by_element(driver, like_button) # not necessary, but good for visual demonstration
        title = ''
        try:
            img = webtools.check_and_get_ele_by_tag_name(photos[i], 'img')
            if img:
                title = img.get_attribute('title')
            if title and title == 'Photo':
                title = 'Untitled'
            driver.execute_script("arguments[0].click();", like_button) 
            done_count = done_count + 1
            printG(f"    - Liked #{str(done_count):3}: '{title:.50}'")
            # pause a randomized time between 0.5 to 1 seconds between actions 
            time.sleep(random.randint(5, 10) / 10)

        except Exception as e:
            message = f'   Error after {str(done_count)}, at index {str(i)}, title {title}:\nException: {e}'
            printR(message)
            return False, message
    return True, ''

#---------------------------------------------------------------
def like_n_photos_on_current_page(driver, number_of_photos_to_be_liked, index_of_start_photo):
    """Like n photos on the active photo page, which is one of the following pages: 
        Popular, 
        Popular from undiscovered photographers, 
        Upcoming, 
        Fresh, 
        Editor's pick, 
        User-specified gallery, 
        User photo page 
    Process:
    - get the list of like-button icons on the page
    - scroll down to the desired photo (index_of_start_photo)
    - for each photo:
      - check whether the photo is already liked, if yes, jump to the next photo, 
      - if no, get the photo tilte or author name, and click on the like-icon to like the photo
      - go to the next photo, scrolling down to load more photo if needed
      
    """
    title = ''
    photographer = ''
    photos_done = 0
    current_index = 0   # the index of the photo in the loaded photos list. We dynamically scroll down the page to load more photos as we go, so ...
                        # ... more photos are appended at the end of the list. We use this current_index to keep track where we were after a list update 

    # getting a list of loaded like-icons (heart icons)
    new_fav_icons = webtools.check_and_get_all_elements_by_css_selector(driver, '.button.new_fav.only_icon')  #'.button.new_fav.only_icon.hearted'
    loaded_photos_count = len(new_fav_icons)

    # waiting a specific time-out until at least one item is loaded 
    time_out = 20
    while loaded_photos_count == 0 and time_out > 0:
        time_out -= 1
        new_fav_icons =  webtools.check_and_get_all_elements_by_css_selector(driver, '.button.new_fav.only_icon')  
        time.sleep(1)
        loaded_photos_count = len(new_fav_icons)

    # Aug 29 2020: Some of the pages use the new page structure (namely, Galleries curated by 500px, users photos pages), 
    # where, among other things, the like button icons are defined differently. 
    # We don't know when and whether the new structure will be used on other pages (namely, Popular, Upcoming, Fresh, Editor's Choice),
    # so we switch to the new algorithm  when the old method failed

    if loaded_photos_count == 0:
        like_n_photos_on_current_page_NEW_PAGE_STRUCTURE(driver, number_of_photos_to_be_liked, index_of_start_photo)
        return

    #optimization: at the begining, scrolling down to the desired index instead of repeatedly scrolling & checking 
    if index_of_start_photo > config.PHOTOS_PER_PAGE:
        estimate_scrolls_needed =  math.floor( index_of_start_photo / config.PHOTOS_PER_PAGE) +1
        webtools.scroll_down(driver, 1, estimate_scrolls_needed, estimate_scrolls_needed, f' - Scrolling down to photos #{index_of_start_photo}:') 
        
        time.sleep(3)
        # instead of a fixed waiting time, we wait until the desired photo to be loaded  
        while loaded_photos_count < index_of_start_photo:
            new_fav_icons = webtools.check_and_get_all_elements_by_css_selector(driver, '.button.new_fav.only_icon')
            loaded_photos_count = len(new_fav_icons)
          
    while photos_done < number_of_photos_to_be_liked: 
        # if all loaded photos have been processed, scroll down 1 time to load more
        if current_index >= loaded_photos_count: 
            prev_loaded_photos = loaded_photos_count
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            # instead of a fixed waiting time, we wait until the desired photo to be loaded, within a given timeout  
            time_out = 30
            while loaded_photos_count <= current_index and time_out > 0:
                time_out -= 1
                new_fav_icons =  webtools.check_and_get_all_elements_by_css_selector(driver, '.button.new_fav.only_icon')  
                time.sleep(2)
                loaded_photos_count = len(new_fav_icons)

            # stop when all photos are loaded
            if loaded_photos_count == prev_loaded_photos:
                break;

        for i in range(current_index, loaded_photos_count + 1):
            current_index += 1

            # skip un-interested items  
            if i < index_of_start_photo : 
                continue     
            
            # stop when limit reaches or when we reload with less items than previous load (in StaleElementReferenceException recovery step below)
            if photos_done >= number_of_photos_to_be_liked or i >= len(new_fav_icons): 
                break     
    
            icon = new_fav_icons[i]
            # skip already liked photo: 'liked' class is a subclass of 'new_fav_only_icon', so these elements are also included in the list
            try:
                if 'heart' in icon.get_attribute('class'): 
                    continue
            except StaleElementReferenceException:
                # DOM has changed. Reload and repeat. ignore this photo if error happens again
                logger.info(f'StaleElementReferenceException on icons element in like_n_photos_on_current_page function, index {i}')
                new_fav_icons =  webtools.check_and_get_all_elements_by_css_selector(driver, '.button.new_fav.only_icon')  
                time.sleep(3)
                try:
                    icon = new_fav_icons[i]
                    if 'heart' in icon.get_attribute('class'): 
                        continue
                except Exception as e:
                    logger.info(f'Second error on icon element in like_n_photos_on_current_page function, index {i}')
                    printR(f'Ignoring photo index {i} due to error locating the like button')
                    continue
                    

            if not config.HEADLESS_MODE:
                webtools.hover_by_element(driver, icon) # not needed, but good to have a visual demonstration
 
            #intentional slowing down a bit to make it look more like human
            time.sleep(random.randint(30, 40)/10)  
            try:
                photo_link = icon.find_element_by_xpath('../../../../..').find_element_by_class_name('photo_link')

            except StaleElementReferenceException:
                # DOM has changed. Reload and repeat
                logger.info(f'StaleElementReferenceException on getting photo_link element in like_n_photos_on_current_page function, photo index: {i}')
                new_fav_icons =  webtools.check_and_get_all_elements_by_css_selector(driver, '.button.new_fav.only_icon')  
                time.sleep(2)
                icon = new_fav_icons[i]
                photo_link = icon.find_element_by_xpath('../../../../..').find_element_by_class_name('photo_link')

            except Exception as e:
                logger.info(f'Exception: {e}')
                printY('   Failed to get the photo link, photo index: {i}')
                # we set this to end the outer loop, while:
                photos_done = number_of_photos_to_be_liked
                break
             
            title =  photo_link.find_element_by_tag_name('img').get_attribute('alt')
            photographer_ele = webtools.check_and_get_ele_by_class_name(photo_link, 'photographer')
            if photographer_ele is not None:
                photographer_ele.location_once_scrolled_into_view
                webtools.hover_by_element(driver, photographer_ele)
                photographer = photographer_ele.text
                photographer_ele.location_once_scrolled_into_view
                webtools.hover_by_element(driver, photographer_ele)
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
            printG(f'   - Liked {str(photos_done):>3}/{number_of_photos_to_be_liked:<3}, {photographer:<28.24}, Photo {str(i+1):<4} title {title:<35.35}')
  
#---------------------------------------------------------------
def like_n_photos_on_current_page_NEW_PAGE_STRUCTURE(driver, number_of_photos_to_be_liked, index_of_start_photo):
    """Like n photos on the active photo page, which is one of the following, as of Aug 29 2020: 
        User-specified gallery, 
        User photo page 
    Process:
    - get the container element that is the parent of all like-button icons
    - from the container, get three lists of elements, Like-buttons elements, Like-statuses elements, and photos elements
    - scroll down to the desired photo (index_of_start_photo)
    - for each like-button on the first list:
      - check whether the photo is already liked by cross-referencing the second list, Like-statuses
      - if yes, jump to the next photo, 
      - if no, get the photo tilte, author name by referencing the third list, photos
      - click on the like-icon to like the photo
      - go to the next photo, scrolling down to load more photo if needed   
    """

    author = ''
    photographer = ''
    photos_done = 0
    current_index = 0   # the index of the photo in the loaded photos list. We dynamically scroll down the page to load more photos as we go, so ...
                        # ... more photos are appended at the end of the list. We use this current_index to keep track where we were after a list update 
    
    user_photos_galley = True
    # determine whether the current page is a 500px's curated gallery, user gallery, or a user photos page
    if 'galleries' in driver.current_url:
        user_photos_galley = False

    time_out = 20
    try:
        container = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.ID, 'justifiedGrid')))
    except TimeoutException:
        printR(f'Timed out {time_out}s while loading photos container. Please try again later')
        return [], ''

    # loaded direct children of container, which are photos elements
    like_buttons, like_statuses = [], []
    childs = webtools.check_and_get_all_elements_by_xpath(container, '*')
    photos = [child for child in childs if child.get_attribute('id') !=  '']
    loaded_photos_count = len(photos)
    if loaded_photos_count == 0:
        printR('No photos are loaded. Please try again later')
        return [], ''
    #scrolling down to the desired index, if needed 
    time_out_countdown = 5
    while time_out_countdown > 0 and loaded_photos_count < index_of_start_photo + number_of_photos_to_be_liked:
        photos[-1].location_once_scrolled_into_view
        time.sleep(1)
        childs = webtools.check_and_get_all_elements_by_xpath(container, '*')
        photos = [child for child in childs if child.get_attribute('id') !=  '']
        loaded_photos_count = len(photos)
        time_out_countdown -= 1

    # in case available photos are less than the number requested
    if time_out_countdown == 0 and loaded_photos_count < index_of_start_photo + number_of_photos_to_be_liked:
        printY(f'Available photos are less than requested. We start from the first photo')
   
    # extract 2 lists of elements
    if loaded_photos_count > 0:
        like_buttons =  [webtools.check_and_get_ele_by_xpath(photo, './/div[@role="button"]') for photo in photos]   
        # the parent of like button element has an attribute that shows whether the photo has been liked or not
        like_statuses =  [webtools.check_and_get_ele_by_xpath(like_button, '..').get_attribute('aria-label') for like_button in like_buttons]

    hide_banners(driver)        
    
    time.sleep(random.randint(10, 15) / 10)   
    if loaded_photos_count == 0:
        printY('   User has no photos')
    done_count = 0

    for i, like_button in enumerate(like_buttons):
        # keep the unwanted element
        if i < index_of_start_photo:
            continue
        like_button.location_once_scrolled_into_view
        # skip already-liked photo. Count it as done 
        if done_count < number_of_photos_to_be_liked and 'Unlike' not in like_statuses[i]:            
            done_count += 1          
            printY(f'    - Liked #{str(done_count):3} : Photo {str(i + 1 + index_of_start_photo):2} - already liked')
            continue        

        # check limit
        if done_count >= number_of_photos_to_be_liked:  
            break
        if not config.HEADLESS_MODE:
            webtools.hover_by_element(driver, like_button) # not necessary, but good for visual demonstration
        author, title = '', ''
        try:
            img = webtools.check_and_get_ele_by_tag_name(photos[i], 'img')
            if img:
                webtools.hover_by_element(driver, img)
                done_count = done_count + 1

                # title is shown if the page is a user photos gallery, otherwise, it is photographer name
                if user_photos_galley:
                    title = img.get_attribute('title')
                    message  = f"    - Liked #{str(done_count):3}: 'Title: {title:.50}'"
                else:
                    img_sib1 =  webtools.check_and_get_ele_by_xpath(img, './following-sibling::p')
                    try:
                        author = img_sib1.get_attribute('innerHTML')
                    except:
                        author = 'undefined'
                    message  = f"    - Liked #{str(done_count):3}: 'Author: {author:.50}'"

            driver.execute_script("arguments[0].click();", like_button) 
            #like_button.click()
             # pause a randomized time between 0.5 to 1 seconds between actions 
            time.sleep(random.randint(5, 10) / 10)
            printG(message)

        except Exception as e:
            printR(f'   Error after {str(done_count)}, at index {str(i)}, {author}, {title}:\nException: {e}')
            return False
    return True

#---------------------------------------------------------------
def play_slideshow(driver, time_interval):
    """Play slideshow of photos on the active photo page in browser.

    PROCESS:
    Expecting the active page in browser is the photos page
    - Open the first photo by click on it
    - Click on the expand arrow to maximize the display area 
    - After a given time interval, locate the next button and click on it to show the next photo
    - Exit when last photo is reached
    """
    photo_links_eles = webtools.check_and_get_all_elements_by_class_name(driver, 'photo_link')
    loaded_photos_count = len(photo_links_eles)
     
    if len(photo_links_eles) > 0:
        # show the first photo
        driver.execute_script("arguments[0].click();", photo_links_eles[0])

        time_out = 60
        try:    
            WebDriverWait(driver, time_out).until( EC.presence_of_element_located((By.ID, 'copyrightTooltipContainer')) )
        except  TimeoutException:
            printR(f'Timed out {time_out}s while loading photo')
            return  
        

        #setup a keypress listener on the document and a variable to store the request
        driver.execute_script('''
            document.requestedInput = 'c';              /* default c for CONTINUE*/
            document.addEventListener("keydown", keyDownPress, false);
            function keyDownPress(e) { 
                if(e.keyCode != 37 && e.keyCode != 39)  /* ignore forward/backward navigation by arrow keys*/
                    if(e.keyCode == 80 )                /* p for PAUSE */
                        document.requestedInput = 'p';              
                    else if (e.keyCode == 67 )          /* c for CONTINUE*/       
                        document.requestedInput = 'c';              
                    else       
                        document.requestedInput = 's';  /* any other keys will be considered as 's', for STOP */                                                       
           } ''')    

        # suppress the sign-in popup that may appear if not login
        hide_banners(driver)        
        
        # locate the expand icon and click it to expand the photo
        expand_icon = webtools.check_and_get_ele_by_xpath(driver, '//*[@id="copyrightTooltipContainer"]/div[1]/div/div[2]')

        if expand_icon is not None:
            expand_icon.click()
        
        #locate the right arrow icon that can be use to navigate to the next photo
        next_icon = webtools.check_and_get_ele_by_xpath(driver,'//*[@id="copyrightTooltipContainer"]/div[1]/div/div[3]/div') 
        time.sleep(time_interval)
        
        #use the next photo icon as a flag to signal the end of the gallery
        while True: #next_icon is not None:
            requested_input = driver.execute_script('return document.requestedInput')
            
            # go to the next photo
            if requested_input == 'c':
                ActionChains(driver).send_keys(Keys.RIGHT).perform()            
            while requested_input == 'p':
                time.sleep(0.5)
                requested_input = driver.execute_script('return document.requestedInput')
            
            if requested_input == 's':
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                return
            time.sleep(time_interval)                
            next_icon = webtools.check_and_get_ele_by_xpath(driver,  '//*[@id="copyrightTooltipContainer"]/div[1]/div/div[3]/div')
                                                            #'//*[@id="copyrightTooltipContainer"]/div/div[2]/div/div[2]')  
    else:
        print('no photo found')

#---------------------------------------------------------------                           
def like_n_photos_on_homefeed_page(driver, user_inputs):
    """Like n photos from the user's home feed page, excluding recommended photos and skipping consecutive apiless.photo(s) of the same user
   
    PROCESS:
    - Expecting the user home feed page is the active page in the browser
    - Get the list elements representing loaded interested photos (the ones from photographers that you are following)
    - For each element in the list, traverse up, down the xml tree for photo title, owner name, like status, and make a decision to click the like icon or not
    - Continue until the required number is reached. along the way, stop and scroll down to load more photos when needed 
    """
    photos_done, loaded_photos_coun  = 0, 0
    current_index = 0  # the index of the photo in the loaded photos list. We dynamically scroll down the page to load more photos as we go, so ...
                       # ... we use this index to keep track where we are after a list update 
    prev_photographer_name = ''
    print(f"    - Getting the loaded photos from {user_inputs.user_name}'s home feed page ...")
 
  
    # get the photos containers
    time_out = 30
    try:
        container = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.ID, 'justifiedGrid')))
    except TimeoutException:
        printR(f'Timed out {time_out}s while loading photos container. Please try again')
        return [], ''

    time.sleep(1)

    like_buttons, like_statuses = [], []

    photos = driver.find_elements_by_xpath('//*[contains(@id, "photo-")]')
    time.sleep(1)
    try:
        img_eles = [webtools.check_and_get_all_elements_by_tag_name(photo, 'img')[1] for photo in photos]
        loaded_photos_count = len(img_eles)
    except:
        printR('Error locating image elements. Please retry.')
        return

   
    while photos_done < user_inputs.number_of_photos_to_be_liked: 
        # check whether we have processed all loaded photos, if yes, scroll down 1 time to load more
        if current_index >= loaded_photos_count: 
            prev_loaded_photos = loaded_photos_count
            photos[-1].location_once_scrolled_into_view
            time.sleep(2)
   
            photos = driver.find_elements_by_xpath('//*[contains(@id, "photo-")]')
            time.sleep(random.randint(10, 15) / 10)   
            img_eles = [webtools.check_and_get_all_elements_by_tag_name(photo, 'img')[1] for photo in photos]
            loaded_photos_count = len(img_eles)            
            
            if not img_eles or (img_eles and len(img_eles)) == 0:
                print(f"    - No photos found on {user_inputs.user_name}'s home feed page")
                return
            loaded_photos_count = len(img_eles)

            # stop when all photos are loaded
            if loaded_photos_count == prev_loaded_photos:
                break;

        for i in range(current_index, loaded_photos_count):
            # stop when done
            if photos_done >= user_inputs.number_of_photos_to_be_liked: 
                break
            current_index += 1
            photographer_name, title = '', ''      
  
            like_button =  webtools.check_and_get_ele_by_xpath(photos[i], './/div[@role="button"]') 
            like_status =  webtools.check_and_get_ele_by_xpath(like_button, '..').get_attribute('aria-label')

            title_ele =  webtools.check_and_get_ele_by_xpath(photos[i], './/div[1]')
            if title_ele:
                title =  title_ele.get_attribute('innerHTML') 

            p_ele = webtools.check_and_get_ele_by_xpath(photos[i], './/div[2]/a/div/p') 
            if p_ele:
                photographer_name = p_ele.get_attribute('innerHTML')

            if 'Unlike' not in like_status:
                photo_already_liked = True
                printW(f'     Already liked: photo {str(i + 1):3}, from {photographer_name:<26.25}, {title:<35.35}')
                continue  
            else:
                # skip consecutive photos of the same photographer if it is the case
                if photographer_name == prev_photographer_name:
                    printY(f'     Skipped:       photo {str(i + 1):3}, from {photographer_name:<26.25}, {title:<35.35}')
                    continue
                # like the photo
                try:
                    if not config.HEADLESS_MODE:
                        webtools.hover_by_element(driver, like_button)
                    time.sleep(random.randint(20, 30)/10)  # slow down a bit to make it look more like a human
                    driver.execute_script("arguments[0].click();", like_button) 
                except Exception as e:
                    logger.info(f'Exception: {e}')
                    printY('Bypass')
                else:
                    photos_done += 1
                    prev_photographer_name = photographer_name
                    printG(f'   - Like {photos_done:>3}/{user_inputs.number_of_photos_to_be_liked:<3}:  photo {str(i + 1):<3}, from {photographer_name:<26.25}, {title:<3.35}')                    
                    prev_photographer_name = photographer_name

#---------------------------------------------------------------
def login(driver, user_inputs):
    """Submit given credentials to the 500px login page. Display error message if error occured. Return True/False loggin status """

    global logged_in
    if len(user_inputs.password) == 0 or len(user_inputs.user_name) == 0 or driver == None: 
        return False
    print(f'    - Logging in user {user_inputs.user_name} ...')
    time_out = 30
    driver.get("https://500px.com/login" )
    try:
        user_name_ele = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.ID, 'emailOrUsername'))) # 'email')))
        user_name_ele.send_keys(user_inputs.user_name) 
        
        pwd_ele = WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.ID, 'password')))
        pwd_ele.send_keys(user_inputs.password) 

        submit_ele =  webtools.check_and_get_ele_by_xpath(user_name_ele, '../following-sibling::button') 
        if submit_ele is not None: 
            submit_ele.click()
        
        # after a sucess login, 500px will automatically load the user's homefeed page. So after submitting the credentials, we
        # wait until one of an element in the login page become unavailable
        WebDriverWait(driver, time_out).until(EC.staleness_of(user_name_ele))
       
    except  NoSuchElementException:
        printR("   Error accessing the login page. Please retry")
        logged_in = False
    except TimeoutException :
        printR(f'   Time out while loading {user_inputs.user_name} home page. Please retry')
        logged_in = False
    except:
        printR(f'   Error loading {user_inputs.user_name} home page. Please retry.')
        logged_in = False
    else:
        # username/password errors
        if webtools.check_and_get_ele_by_class_name(driver, 'error') is not None or \
           webtools.check_and_get_ele_by_class_name(driver, 'not_found') is not None or \
           webtools.check_and_get_ele_by_class_name(driver, 'missing') is not None:   
           printR(f'Error on loggin. Please retry with valid credentials')
           user_inputs.user_name, user_inputs.password,  user_inputs.db_path = ('' for i in range(3))
           logged_in = False
        logged_in = True
        printG('     OK')

#---------------------------------------------------------------
def hide_banners(driver):
    """Hide or close popup banners that make elements beneath them inaccessible. And click away the sign-in window if it pops up.
    
    Specifically, top banner is identified by the id 'hellobar',
    Bottom banners are identified by tag 'w-div' and
    Sign-up banner is identified by class 'join_500px_banner_close_ele'
    """

    top_banner = webtools.check_and_get_ele_by_id(driver, 'hellobar')
    if top_banner is not None:
        try:
            driver.execute_script("arguments[0].style.display='none'", top_banner)
        except:
            pass

    bottom_banners = webtools.check_and_get_all_elements_by_tag_name(driver, 'w-div')
    for banner in bottom_banners:
        close_ele = webtools.check_and_get_ele_by_tag_name(banner, 'span')
        if close_ele is not None:
            try:
                driver.execute_script("arguments[0].click();", close_ele)
            except:
                pass   

    join_500px_banner_close_ele = webtools.check_and_get_ele_by_class_name(driver, 'unified_signup__close')
    if join_500px_banner_close_ele is not None:
        try:
            driver.execute_script("arguments[0].click();", join_500px_banner_close_ele)
        except:
            pass

#---------------------------------------------------------------
def show_menu(user_inputs, special_message=''):
    """ Display main menu. Validate and accept these inputs from users: user name, password  and the desired option. 
    
    - Inputs are stored in the user_inputs objects, which is passed by reference.  
    - The return value is a string containing either 'r', 'q' or any digit characters
    - The special_message, if given, will be displayed near the end of the menu. It could be used as an alert, warning or error
      from the last operation.
    """

    printC('')
    printC('--------- Chose one of these options: ---------')
    printY('      The following options require a user name:', write_log=False)
    printC('   1  Get user summary')
    printC('   2  Get user photos list (login is optional)')
    printC('   3  Get followers list')
    printC('   4  Get followings list')
    printC('   5  Check if a user is following you')

    printC('')
    printY('      The following options require login:', write_log=False)
    printC('   6  Get users who liked a given photo')
    printC('   7  Get n last notifications (max 5000) and the unique users on it')
    printC('')
    printC('   8  Like n photos from a given user')
    printC('   9  Like n photos, starting at a given index, on various photo pages') 
    printC('  10  Like n photos of each user who likes a given photo or yours')
    printC('  11  Like n photos from your home-feed page, excluding recommended photos ')
    printC('  12  Like n photos from the last m users in the notifications')
    printC('')
    printY('      The following option does not need credentials:', write_log=False)
    printC('  13  Play slideshow on a given gallery (login is optional)')
    printC('')
    printY('      Data Analysis:', write_log=False)
    printC('  14  Update local database from the latest csv files on disk')
    printC('  15  Categorize users based on following statuses')
    printC('  16  Notification analysis')

    printC('')
 
    printC('   r  Restart with different user')
    printC('   q  Quit')
    printC('')
  
    if special_message:
        printY(special_message)
  
    sel, abort = utils.validate_input('Enter your selection >', user_inputs)

    if abort:
        return 

    sel = int(sel)
    # No credentials needed for playing slideshow
    if sel == 13:
        user_inputs.choice = str(sel)
        return 
    
    # user name is mandatory for all options, except playing the slideshow
    if user_inputs.user_name == '':
        user_inputs.user_name = input('Enter 500px user name >')
        user_inputs.db_path = os.path.join(config.OUTPUT_PATH, f'500px_{user_inputs.user_name}.db')  
        user_inputs.main_html_page = os.path.join(config.OUTPUT_PATH, f'500px-APIless_{user_inputs.user_name}.html')
        user_inputs.js_file_name   = os.path.join(config.OUTPUT_PATH, rf'javascripts\dynamic_menu_{user_inputs.user_name}.js')

        # generate the main html file that hosts all the result html files
        if not os.path.isfile(user_inputs.main_html_page):
            htmltools.create_main_html_page(user_inputs.main_html_page, user_inputs.user_name)

        # generate a javascript file that handles the dynamic menu on the main html page 
        #if not os.path.isfile(user_inputs.js_file_name):
        utils.create_menu_items(user_inputs.user_name, config.OUTPUT_PATH, user_inputs.js_file_name)

    printG(f'Current user: {user_inputs.user_name}', write_log=False)

    # analysis for users' relationship and creating local database options need nothing else
    if 14 <= sel <= 16:
        user_inputs.choice = str(sel)
        return 

    # password is optional:
    if (sel == 2) and user_inputs.password == '':
        if sel == 2:
            printY('Optional: logged-in user can see the galleries featuring their photos.')
 
        printY('Type in your password or just press ENTER to ignore', write_log=False)
        expecting_password = utils.win_getpass(prompt='Password >')
        if expecting_password == 'q' or expecting_password == 'r': #change of mind: quit or reset
            user_inputs.choice = expecting_password
            return True 
        if len(expecting_password) > 0:
            user_inputs.password = expecting_password

            
    if sel <= 5:
        user_inputs.choice = str(sel)
        return
    
    # password is mandatory ( quit or restart are also possible at this step )
    if sel >= 6 :
        if user_inputs.user_name == '':
            user_inputs.user_name, abort = utils.validate_non_empty_input('Enter 500px user name >', user_inputs)
            if abort:
                return

        if user_inputs.password == '' and sel != 97:
            user_inputs.password, abort =  utils.validate_non_empty_input('Enter password >', user_inputs)
            if abort:
                return
    
    user_inputs.choice = str(sel)        

#---------------------------------------------------------------
def show_galllery_selection_menu(user_inputs):
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
    printY('    r  Restart for different user', write_log=False)
    printY('    q  Quit', write_log=False)

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
        input_val, abort = utils.validate_non_empty_input(('Enter the link to your desired photo gallery.\n'
                             'It could be a public gallery with filters, or a private gallery >'), user_inputs)
        if abort:
            return '', '', True
        else:
            return input_val, f'User-specified gallery: {input_val.split("/")[-1]}', False

    elif sel == '7': return f'https://500px.com/{user_inputs.user_name}'                  , 'My photos', False

    else:
        printR('Invalid input, please select again.')
        return show_galllery_selection_menu(user_inputs)

#---------------------------------------------------------------
def define_and_read_command_line_arguments(): 
    """ Define all optional user inputs and their default values. Then fill in with the actual values from command lines.
        Return a user_inputs objects filled with given arguments. 

    All command line arguments are optional (as opposed to postional).  If the argurment '--choice' is not set, all other arguments will be ignored whether 
    they are set or not, and the attribute "use_command_line_args" will be set to false 
    """
    
    user_inputs = apiless.UserInputs()
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
        if config.DEBUG:
            print(f'    {dict_name}: {args_dict[dict_name]}')
        setattr(user_inputs, dict_name, args_dict[dict_name])
    # if a choice is provided from the command line, we will switch to command line mode. 
    if user_inputs.choice != '0':
        user_inputs.use_command_line_args = True
    return user_inputs

#---------------------------------------------------------------
def get_additional_user_inputs(user_inputs):
    """ Ask the user for additional inputs based on the option previously selected in user_inputs.choice.  

    Allow the user to abort (quit or restart) anytime during the input reception. return false if aborting, true otherwise """

    abort = False
    if user_inputs.choice == 'q' or user_inputs.choice == 'r':
        return False

    # no additional input are required for options from 1 to 5
    choice = int(user_inputs.choice)
    if choice < 5:
        return True

    # 5. Check if a user is following you : target user name
    elif choice == 5:
        user_inputs.target_user_name , abort =  utils.validate_non_empty_input('Enter target user name >', user_inputs)
 
    # 6. Get a list of users who liked a given photo: photo_href
    elif choice == 6: 
        user_inputs.photo_href, abort = utils.validate_non_empty_input('Enter your photo href >', user_inputs)
  
    # 7. Get n last notifications (max 5000) and the unique users on it: number_of_notifications 
    elif choice == 7 : 
        input_val, abort =  utils.validate_input(f'Enter the number of notifications you want to retrieve(1-{config.MAX_NOTIFICATION_REQUEST}) >', user_inputs)
        if abort: 
            return False
        else:
            num1 = int(input_val)
            user_inputs.number_of_notifications = num1 if num1 < config.MAX_NOTIFICATION_REQUEST else config.MAX_NOTIFICATION_REQUEST

        input_val, abort =  utils.validate_input('Enter the desired 1-based start index >', user_inputs)
        if abort: 
            return False
        else:
            num2 = int(input_val)
            if num2 > 0:
                num2 -= 1   # we have asked a 1-based number, so we convert it back to 0-based  
            user_inputs.index_of_start_notification = num2 if num2 < config.MAX_NOTIFICATION_REQUEST -  user_inputs.number_of_notifications else \
                                                      config.MAX_NOTIFICATION_REQUEST - user_inputs.number_of_notifications
  
    # common input for 8 to 11: number of photo to be auto-liked
    elif choice >= 8 and choice <= 11:
        input_val, abort =  utils.validate_input(f'Enter the number of photos you want to auto-like (1-{config.MAX_AUTO_LIKE_REQUEST})>', user_inputs)
        if abort:
            return False
        else: 
            num = int(input_val)
            user_inputs.number_of_photos_to_be_liked = num if num < config.MAX_AUTO_LIKE_REQUEST else config.MAX_AUTO_LIKE_REQUEST         

        # 8.  Like n photos from a given user: target_user_name
        if choice == 8: 
            user_inputs.target_user_name, abort = utils.validate_non_empty_input('Enter target user name >', user_inputs)

        # 9.  Like n photos, starting at a given index, on various photo pages:  gallery_href, index_of_start_photo
        elif choice == 9:  
            # gallery selection
            user_inputs.gallery_href, user_inputs.gallery_name, abort = show_galllery_selection_menu(user_inputs)
            if abort:
                return False
            
            input_val, abort =  utils.validate_input('Enter the index of the start photo (1-500) >', user_inputs)
            if abort:
                return False  
            else: 
                input_int = int(input_val)
                if input_int > 0:
                    input_int -= 1   # we asked the end-user to use 1-based number (1-500)                
                user_inputs.index_of_start_photo = input_int

        # 10.  Like n photos of each user who likes a given photo or yours:
        elif choice == 10: 
            #photo_href
            user_inputs.photo_href, abort =  utils.validate_non_empty_input('Enter your photo href >', user_inputs)
    
    # 12. Like n photos from the last m users in the notifications       
    elif choice == 12: 
        input_val, abort = utils.validate_input(f'Enter the number of users you want to process(max {config.MAX_NOTIFICATION_REQUEST}) >', user_inputs)
        if abort: 
            return False
        else: 
            num = int(input_val)
            user_inputs.number_of_notifications = num if num < config.MAX_NOTIFICATION_REQUEST else config.MAX_NOTIFICATION_REQUEST

        input_val, abort = utils.validate_input('Enter the number of photos you want to auto-like for each user >', user_inputs)
        if abort:
            return False
        else: 
            num = int(input_val)
            user_inputs.number_of_photos_to_be_liked = num if num < config.MAX_AUTO_LIKE_REQUEST else config.MAX_AUTO_LIKE_REQUEST

    # 13.  Play slideshow on a given gallery 
    elif choice == 13:
        # allow a login for showing NSFW (not suitable for work) contents
        if user_inputs.password == '':
            printY('If you want to show NSFW contents, please login.', write_log=False)
            if user_inputs.user_name == '':            
                printY(' Type in your user name or just press ENTER to ignore', write_log=False)
                expecting_user_name = input('User name >')
                if expecting_user_name  == 'q' or expecting_user_name  == 'r':
                    user_inputs.choice = expecting_user_name
                    return False               
                if len(expecting_user_name) > 0:
                    user_inputs.user_name = expecting_user_name

            # user name has been entered
            if user_inputs.user_name != '':  
                printY('Type in your password or just press ENTER to ignore', write_log=False)
                expecting_password = utils.win_getpass(prompt='Password >')
                if expecting_password == 'q' or expecting_password == 'r':
                    user_inputs.choice = expecting_password
                    return True 
                if len(expecting_password) > 0:
                    user_inputs.password = expecting_password

        user_inputs.gallery_href, user_inputs.gallery_name, abort = show_galllery_selection_menu(user_inputs)
        if abort:
            return False

        input_val, abort = utils.validate_input('Enter the interval time between photos, in second>', user_inputs)
        if abort:
            return False
        else:
            user_inputs.time_interval = int(input_val)

            printY('To pause, press p', write_log=False)
            printY('To continue, press c', write_log=False)
            printY('To stop, press any other keys.', write_log=False)
            printY('You can use Left/Right arrow keys to manually navigate backward/forward.', write_log=False)
            printY(f'Now press ENTER to start the slideshow {user_inputs.gallery_name}.', write_log=False)
            wait_for_enter_key = input() 
 
    # Options not yet available from the menu:
    # 99. (in progress) Get following statuses of users you are following ( user_name, start index, number_of_users)
    # 98. Like n photos from each of m users, starting at a given start index, from a given csv files
    # more to come ...
    elif choice >= 98 :
        # number of followers
        input_val, abort = utils.validate_input('Enter the number of followers you want to process >', user_inputs)
        if abort:
            return False  
        else: 
            user_inputs.number_of_users = int(input_val)

        # start index of the user
        input_val, abort = utils.validate_input('Enter the user start index (1-based)>' , user_inputs)
        if abort:
            return False  
        else: 
            int_val = int(input_val)
            # the end user will use 1-based index, so we will convert the input to 0-based
            if int_val > 0: int_val -= 1
            user_inputs.index_of_start_user = int_val 
        
        if choice == 98:
            #number of photos
            input_val, abort = utils.validate_input('Enter the number of photos you want to auto-like >', user_inputs)
            if abort:
                return False
            else: 
                num = int(input_val)
                user_inputs.number_of_photos_to_be_liked = num if num < config.MAX_AUTO_LIKE_REQUEST else config.MAX_AUTO_LIKE_REQUEST 
        
            # full file name of the cvs file 
            user_inputs.csv_file, abort =  utils.validate_non_empty_input('Enter the csv full file name>', user_inputs)
            if abort: 
                return False       
            else:
                user_inputs.csv_file =user_inputs.csv_file.replace("\"", "").replace("\'", "") 
        return True
    if abort:
        return False  
    
#--------------------------------------------------------------- 
def show_result_in_browser(html_file_name):
    """ Show the given html file on the global selenium's webdriver. Start a new one if it is not yet created """

    global web_browser_for_result
    if not web_browser_for_result:
        web_browser_for_result = webtools.start_result_web_browser() 
    
    try:
        web_browser_for_result.get(html_file_name)
    except WebDriverException:
        # if the browser has been closed, we will get 'chrome not reachable' exception. If it is the case, start a new one
        web_browser_for_result = webtools.start_result_web_browser() 
        web_browser_for_result.get(html_file_name)

    # if the browser has been minimized, or is an inactive state, this trick will activate and bring the window to the front,
    # but it will get exception if it is already maximized
    try:
        web_browser_for_result.maximize_window()
    except WebDriverException:
        pass

#---------------------------------------------------------------
def handle_option_1(driver, user_inputs, output_lists):
    """ Get user status."""

    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.strftime(config.DATE_FORMAT)

    html_file_name =  os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_user_summary_{date_string}.html')
    printG(f"1. Getting {user_inputs.user_name}'s summary:")

    # do task   
    stats, error_message = get_user_summary(driver, user_inputs, output_lists) 
    if error_message:
        printR('   - ' + error_message)
        if user_inputs.use_command_line_args == False:
            show_menu(user_inputs, error_message)
            return
    user_stats_dict = {'Option 1 '      : '<b>Get user summary', 
                       'Date processed' : time_start.strftime("%b %d %Y"),
                       'Data file'      : os.path.basename(html_file_name)}
    detail_dict = stats.to_dict()
    user_stats_dict.update(detail_dict)

    html_string = htmltools.dict_to_html(user_stats_dict, table_id='user_summary', title = 'User Summary')

    # write result to html file, show it on browser
    utils.write_string_to_text_file(html_string, html_file_name, 'utf-16')

    # update the javascript used in the main html page to use the just created html result page
    utils.update_active_page_on_main_html_page_js(user_inputs.js_file_name, apiless.CSV_type.user_summary.name, os.path.basename(html_file_name))
    show_result_in_browser(user_inputs.main_html_page)
   
    # print summary report
    printG(f"   File saved at: {os.path.basename(html_file_name)}")
    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")
    
#---------------------------------------------------------------
def handle_option_2(driver, user_inputs, output_lists):
    """ Get user photos """

    global logged_in
    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.strftime(config.DATE_FORMAT)
    printG(f"2. Getting {user_inputs.user_name.capitalize()}'s photos list:")
    # avoid to do the same thing twice: if list (in memory) has items AND output file (on disk) exists
    if output_lists.photos is not None and len(output_lists.photos) > 0:
        html_file_name = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{len(output_lists.photos)}_photos_{date_string}.html')
        if  os.path.isfile(html_file_name):
            printY(f'Results exists in memory and on disk. Showing the existing file at:\n{os.path.abspath(html_file)} ...', write_log=False)

           # update the javascript used in the main html page to use the just created html result page
            utils.update_active_page_on_main_html_page_js(user_inputs.js_file_name, apiless.CSV_type.photos_public.name, os.path.basename(html_file_name))
            show_result_in_browser(user_inputs.main_html_page)

            ans = input('This file will be overidden if you want to redo. Proceed ? (y/n)')
            if ans == 'n' : 
                return

    # if user provided password then login (logged-in users can see the galleries that feature theirs photos
    if user_inputs.password != '' and not logged_in:
        login(driver, user_inputs)
        if not logged_in:
            printR('     Error logging in. Featured galleries will not be extracted.')
    hide_banners(driver)
  
    # main task
    top_photos_html_string, public_photos_table_string, unlisted_photos_table_string, limited_access_photos_table_string = '', '', '', ''
    if not logged_in:
        print('    - Getting Public photos ...')    
        output_lists.photos, csv_public_photos_file, public_photos_table_string = process_photo_group(driver, user_inputs, output_lists, 
                     f'https://web.500px.com/{user_inputs.user_name}', date_string, apiless.CSV_type.photos_public, config.USE_LOCAL_THUMBNAIL)
    else:
        # 1. unlisted photos
        print('    - Getting Unlisted photos ...')
        output_lists.photos_unlisted, csv_unlisted_file, unlisted_photos_table_string = process_photo_group(driver, user_inputs, output_lists, 
                    'https://web.500px.com/manage/unlisted', date_string, apiless.CSV_type.photos_unlisted, config.USE_LOCAL_THUMBNAIL)

        # 2. limited access photos
        print('    - Getting Unlimitted Access photos ...')
        output_lists.photos_limited_access, csv_limited_access_file, limited_access_photos_table_string = process_photo_group(driver, user_inputs, output_lists, 
                     'https://web.500px.com/manage/limited_access', date_string, apiless.CSV_type.photos_limited_access, config.USE_LOCAL_THUMBNAIL)

        # 3. public photos
        print('    - Getting Public photos ...')    
        output_lists.photos, csv_public_photos_file, public_photos_table_string = process_photo_group(driver, user_inputs, output_lists, 
                     'https://web.500px.com/manage/public', date_string, apiless.CSV_type.photos_public, config.USE_LOCAL_THUMBNAIL)

    # 4. create a description table
    description_html_string = ''
    desc_dict = {'Option 2'     : '<b>Get photos list', 
                 'Date processed':  time_start.strftime("%b %d %Y"),
                 'User'          : user_inputs.user_name, 
                 'Data file'     : os.path.basename(csv_public_photos_file) }

    # 5. create a top-photos list
    # 6. create a statistics (overview) dictionary
    top_photos_csv_file_name, stats_dict = create_top_photos_and_statistics(user_inputs.user_name, output_lists.photos)
    
    # Convert the top-photos csv to a html table
    if top_photos_csv_file_name != "":
        top_photos_html_string = htmltools.CSV_top_photos_list_to_HTML_table(top_photos_csv_file_name, output_lists, use_local_thumbnails = config.USE_LOCAL_THUMBNAIL,  
                                 ignore_columns = ['ID', 'Author Name', 'Href', 'Thumbnail Href', 'Thumbnail Local', 'Rating', 'Date', 'Category', 'Tags'], headline_tag='h4')

    # assemble all html table into one section
    all_photos_sections_html_string =(f'{top_photos_html_string}\n\n'
                                      f'{unlisted_photos_table_string}\n\n'
                                      f'{limited_access_photos_table_string}\n\n'
                                      f'{public_photos_table_string}\n\n')

    # write everything to a html page  
    html_file_name = htmltools.write_html_page( csv_public_photos_file, apiless.CSV_type.photos_public, output_lists, 
                                                description_dict = desc_dict, 
                                                statistics_info = stats_dict,
                                                page_title = f'Photos list ({len(output_lists.photos)})',
                                                photos_html_string = all_photos_sections_html_string)

   # update the javascript used in the main html page to use the just created html result page
    utils.update_active_page_on_main_html_page_js(user_inputs.js_file_name, apiless.CSV_type.photos_public.name, os.path.basename(html_file_name))
    show_result_in_browser(user_inputs.main_html_page)
    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")

#---------------------------------------------------------------
def handle_option_3(driver, user_inputs, output_lists):
    """ Get followers"""
    
    global logged_in
    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.strftime(config.DATE_FORMAT)
    printG(f"3. Getting the list of users who follow {user_inputs.user_name}:")

    # avoid to do the same thing twice: when the list (in memory) has items and output file exists on disk
    if output_lists.followers_list is not None and len(output_lists.followers_list) > 0:
        html_file_name = f'{user_inputs.user_name}_{len(output_lists.followers_list)}_followers_{date_string}.html'
        if os.path.isfile(html_file_name):
            printY(f'Results exists in memory and on disk. Showing the existing file at:\n{os.path.abspath(html_file_name)} ...', write_log=False)

        # update the javascript used in the main html page to use the just created html result page
        utils.update_active_page_on_main_html_page_js(user_inputs.js_file_name, apiless.CSV_type.followers.name, os.path.basename(html_file_name))
        show_result_in_browser(user_inputs.main_html_page)
        return
   
    # main task    
    hide_banners(driver)
    output_lists.followers_list = get_followers_list(driver, user_inputs, output_lists)
    
    # write result to csv, convert it to html, show html in browser
    if output_lists.followers_list is not None and len(output_lists.followers_list) > 0:
        csv_file_name = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{len(output_lists.followers_list)}_followers_{date_string}.csv')  
        
        # write description section: a h4 headline and a table   
        desc_dict = {'Option 3'       : f"<b>Get followers list",
                     'Date processed' : time_start.strftime("%b %d %Y"),
                     'User'           : user_inputs.user_name,
                     'Data file'      : os.path.basename(csv_file_name)}

        if utils.write_users_list_to_csv(output_lists.followers_list, csv_file_name) == False:
            printR(f'   Error writing the output file\n:{csv_file_name}')
            return

        # write main items in csv file and everything else to the result html page  
        html_file_name = htmltools.write_html_page( csv_file_name, apiless.CSV_type.followers, output_lists, 
                                                    description_dict= desc_dict, 
                                                    page_title = f'List of  {len(output_lists.followers_list)} followers',
                                                    use_local_thumbnails = config.USE_LOCAL_THUMBNAIL, 
                                                    ignore_columns=['Avatar Href', 'Avatar Local', 'User Name', 'ID', 'Relationship'], 
                                                    headline_tag='h4')
       # update the javascript used in the main html page to use the just created html result page
        utils.update_active_page_on_main_html_page_js(user_inputs.js_file_name, apiless.CSV_type.followers.name, os.path.basename(html_file_name))
        show_result_in_browser(user_inputs.main_html_page)
   
    else:
        printR('The Followers list is empty')

    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")
 
#---------------------------------------------------------------
def handle_option_4(driver, user_inputs, output_lists):
    """ Get followings (friends)"""
    
    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.strftime(config.DATE_FORMAT)
    printG(f"4. Getting the list of users that {user_inputs.user_name} is following:") 

    # avoid to do the same thing twice: when the list (in memory) has items and output file exists on disk
    if output_lists.followings_list is not None and len(output_lists.followings_list) > 0:
        # find the latest html file on disk and show it
        files = [f for f in glob.glob(output_lists.output_dir + f"**/{user_inputs.user_name}*followings*.html")]
        files.sort(key=lambda x: os.path.getmtime(x))
        html_file = files[-1]
        printY(f'Results exists in memory and on disk. Showing the existing file at:\n{os.path.abspath(html_file)} ...', write_log=False)

       # update the javascript used in the main html page to use the just created html result page
        utils.update_active_page_on_main_html_page_js(user_inputs.js_file_name, apiless.CSV_type.followings.name, os.path.basename(html_file_name))
        show_result_in_browser(user_inputs.main_html_page)

        ans = input('This file will be overidden if you want to redo. Proceed ? (y/n)')
        if ans == 'n' : 
            return

    # main task
    output_lists.followings_list = get_followings_list(driver, user_inputs, output_lists)
    
    # write result to csv, convert it to html, show html in browser
    if output_lists.followings_list is not None and len(output_lists.followings_list) > 0:
        csv_file_name = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{len(output_lists.followings_list)}_followings_{date_string}.csv')
         
        # write description section: a h4 headline and a table   
        description_dict = {'Option 4'       : f"<b>Get followings list", 
                            'Date processed' : time_start.strftime("%b %d %Y"),
                            'User'           : user_inputs.user_name, 
                            'Data file'      : os.path.basename(csv_file_name) }

        if utils.write_users_list_to_csv(output_lists.followings_list, csv_file_name) == False:
            printR(f'   Error writing the output file\n:{csv_file_name}')
            return

        # write main items in csv file and everything else to the result html page  
        html_file_name = htmltools.write_html_page( csv_file_name, apiless.CSV_type.followings, output_lists, 
                                                    description_dict= description_dict, 
                                                    page_title = f'List of {len(output_lists.followings_list)} users you are following',
                                                    use_local_thumbnails = config.USE_LOCAL_THUMBNAIL, 
                                                    ignore_columns=['Avatar Href', 'Avatar Local', 'User Name', 'ID', 'Relationship'], 
                                                    headline_tag='h4')

       # update the javascript used in the main html page to use the just created html result page
        utils.update_active_page_on_main_html_page_js(user_inputs.js_file_name, apiless.CSV_type.followings.name, os.path.basename(html_file_name))
        show_result_in_browser(user_inputs.main_html_page)
    else:
        printR('The Following list is empty')

    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")

#---------------------------------------------------------------
def handle_option_6(driver, user_inputs, output_lists):
    """ Get a list of users who liked a given photo."""
    
    global logged_in
    time_start = datetime.datetime.now().replace(microsecond=0) 
    date_string = time_start.strftime(config.DATETIME_FORMAT)   
    printG(f"5. Getting the list of unique users who liked the given photo:")

    # if user provided password then login
    if user_inputs.password != '' and not logged_in:
        login(driver, user_inputs)
        if not logged_in:
            printR('     Error logging in. The following statuses of users will not be known')
    try:
        driver.get(user_inputs.photo_href)
    except:
        printR(f'   Invalid href: {user_inputs.photo_href}. Please retry.')
        show_menu(user_inputs)        
        return

    # main task
    time.sleep(1)
    hide_banners(driver)
    output_lists.like_actioners_list, details_dict = get_like_actioners_list(driver, user_inputs, output_lists, get_name_only = False)
    if len(output_lists.like_actioners_list) == 0:
        return
    
    csv_file_name = details_dict['Data file']
    page_title = details_dict['Title']
      
    # write result to csv, convert it to html, show html in browser
    if len(output_lists.like_actioners_list) == 0 or utils.write_users_list_to_csv(output_lists.like_actioners_list, csv_file_name) == False:
        return
 
   # get stats
    # No,Avatar Href,Avatar Local,Display Name,User Name,ID,Followers Count,Relationship
    df = utils.CSV_file_to_dataframe(csv_file_name)
    followings_count  = df.loc[df.Relationship == 'Following', "Relationship"].shape[0] if logged_in else '<i>Unknown: user did not log in'
    not_follows_count  = df.loc[df.Relationship == 'Not Follow', "Relationship"].shape[0] if logged_in else '<i>Unknown: user did not log in'
    unknowns_count     = df.loc[df.Relationship == 'Unknown', "Relationship"].shape[0]

    description_dict = {'Option 5'       : f"<b>Get users who liked a given photo", 
                        'Date processed' : time_start.strftime("%b %d %Y"),
                        'User'           : user_inputs.user_name,
                        'Data file'      : os.path.basename(csv_file_name),
                        'Following'      : str(followings_count),
                        'Not Follow'     : str(not_follows_count),
                        'Unknown'        : str(unknowns_count) }

    if utils.write_users_list_to_csv(output_lists.like_actioners_list, csv_file_name) == False:
        printR(f'   Error writing the output file\n:{csv_file_name}')
        return

    # write everything to an html page
    html_file_name = htmltools.write_html_page( csv_file_name, apiless.CSV_type.like_actors, output_lists, 
                                                description_dict= description_dict, 
                                                page_title = page_title,
                                                use_local_thumbnails = config.USE_LOCAL_THUMBNAIL, 
                                                ignore_columns = ['Avatar Href', 'Avatar Local', 'User Name', 'ID'], 
                                                headline_tag='h4')
   # update the javascript used in the main html page to use the just created html result page
    utils.update_active_page_on_main_html_page_js(user_inputs.js_file_name, apiless.CSV_type.like_actors.name, os.path.basename(html_file_name))
    show_result_in_browser(user_inputs.main_html_page)

    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")

#---------------------------------------------------------------
def handle_option_5(driver, user_inputs, output_lists):
    """Check if a user is following you."""

    time_start = datetime.datetime.now().replace(microsecond=0)
    printG(f"6. Check if user {user_inputs.target_user_name} follows {user_inputs.user_name}:")

    # check the status from recorded data first
    # find the latest all_users csv file on disk
    all_users_file = utils.get_latest_file(output_lists.output_dir, user_inputs.user_name, apiless.CSV_type.all_users, file_extenstion = 'csv', print_info = False)  
    if all_users_file != '':
        print(f'    - According to the local database:')
        df = utils.CSV_file_to_dataframe(all_users_file)
        df_match = df[df['User Name'].str.lower() == user_inputs.target_user_name.lower()]
        if df_match.shape[0] == 0:
            print(f'     No relationship with {user_inputs.target_user_name}') 
        else:
            relationship = df_match.Relationship.values[0]
            if relationship == 'Reciprocal':
                printG(f'     You and {user_inputs.target_user_name} follow each other')
            elif relationship == 'Not Follow':
                printY(f'     {user_inputs.target_user_name} follows you. You do not follow back')
            elif relationship == 'Following':
                printR(f'     You follow {user_inputs.target_user_name} without being followed back')
        
        ans = input('Do you want to verify the latest status online (y/n)? >')
        if ans == 'n':
            return
    # check following status online
    result, message = does_this_user_follow_me(driver, user_inputs)

    if result == True:
        printG('   - ' + message)
    else:
        printR('   - ' + message)
    
    printG(f'   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s') 

#---------------------------------------------------------------
def handle_option_7(driver, user_inputs, output_lists):
    """ Get n last notifications details (max 5000). Show the detail list and the list of the unique users on it"""

    global logged_in
    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.strftime(config.DATETIME_FORMAT)
    if user_inputs.number_of_notifications == -1:
        option = f"Getting up to {config.MAX_NOTIFICATION_REQUEST} notifications"
    elif user_inputs.index_of_start_notification > 0:
        option = f"Getting {user_inputs.number_of_notifications} notifications, starting from index {user_inputs.index_of_start_notification + 1}"
    else: 
        option = f"Getting the last {user_inputs.number_of_notifications} notifications"
    printG(f'7. {option}:')
    html_file = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{user_inputs.number_of_notifications}_notifications_{date_string}.html')

    # avoid to do the same thing twice: when the list (in memory) has items and output file exists on disk
    if output_lists.notifications is not None and len(output_lists.notifications) > 0 and os.path.isfile(html_file):
        printY(f'   Results exists in memory and on disk. Showing the existing file at:\n{os.path.abspath(html_file)} ...', write_log=False)        
        utils.show_html_file(html_file)
        return 
    
    # if user provided password then login
    if user_inputs.password != '' and not logged_in:
        login(driver, user_inputs)
        if not logged_in:
            return 

    # after a login, user's homefeed page will automatically loaded. We don't this page, nor to waste time waiting for it to complete, 
    # so we force a hard stop asap
    time_out = 40
    try:
        WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.XPATH, '/html/body')))
        driver.execute_script("window.stop();") 
    except TimeoutException:
        pass # silently forget about it

    #then we load the desired page
    driver.get('https://500px.com/notifications')
    #time.sleep(1)
    print('    - Getting notification list ...')
    try:
        WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.CLASS_NAME, 'notification_item')))
    except TimeoutException:
        printR(f'Timed out {time_out}s while loading notifications list. Please try again later')
        return
        
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    hide_banners(driver)

    # do task 1 of 2: get notifications
    output_lists.notifications = get_notification_list(driver, user_inputs, output_lists)[0]
    if len(output_lists.notifications) == 0 and len(output_lists.unique_notificators) == 0:
        show_menu(user_inputs)
        return 
    # read notifications objects into a dataframe
    df_notif = pd.DataFrame.from_records([item.to_dict() for item in output_lists.notifications])   #or utils.CSV_file_to_dataframe(csv_file)        
 
    #  write statictics section: a h4 headline and a table  
    stats_dict = utils.get_notifications_statistics(df_notif)  

    # Write the notification list to csv and html, show html in browser     
    file_name =  f'{user_inputs.user_name}_{len(output_lists.notifications)}_notifications_{date_string}' 
    csv_file_name  = os.path.join(output_lists.output_dir, f'{file_name}.csv')

    # write description section: a h4 headline and a table   
    description_dict = {'Option 7 (1 of 2)' : f'<b>Get {user_inputs.number_of_notifications} notifications, starting from index {user_inputs.index_of_start_notification + 1}', 
                        'Date processed'    : time_start.strftime("%b %d %Y"),
                        'User'              : user_inputs.user_name,
                        'Data file'         : os.path.basename(csv_file_name)}
   
    # write notification list csv file and everything else to an html page
    if len(output_lists.notifications) > 0 and  utils.write_notifications_to_csvfile(output_lists.notifications, csv_file_name) == True:
       html_file_name = htmltools.write_html_page( csv_file_name, apiless.CSV_type.notifications, output_lists, 
                                                    description_dict= description_dict, 
                                                    statistics_info = stats_dict, 
                                                    page_title = f'List of {len(output_lists.notifications)} notifications',
                                                    use_local_thumbnails = config.USE_LOCAL_THUMBNAIL, 
                                                    ignore_columns = ['Avatar Href', 'Avatar Local', 'User Name', 'ID', 'Photo Thumbnail Href', 'Photo Thumbnail Local', 'Photo Link'], 
                                                    headline_tag='h4')
   # update the javascript used in the main html page to use the just created html result page
    utils.update_active_page_on_main_html_page_js(user_inputs.js_file_name, apiless.CSV_type.notifications.name, os.path.basename(html_file_name))
    show_result_in_browser(user_inputs.main_html_page)

    # do task 2 of 2:Process Unique users list with detailed analysis, write to csv, html and show html 
    df_unique, stats_list = process_unique_users(df_notif, user_inputs.user_name, output_lists.output_dir)

    csv_file_name  = os.path.join(config.OUTPUT_PATH,  
                f"{user_inputs.user_name}_{str(df_unique.shape[0])}_unique_users_in_{len(output_lists.notifications)}_notifications_{date_string}.csv")
 
    # write unique users list to csv file
    df_unique.to_csv(csv_file_name, encoding='utf-16', index = False)

    # write description section: a h4 headline and a table 
    description_dict = {'Option 7 (2 of 2)' : f"<b>Extract unique users in {user_inputs.number_of_notifications} notifications", 
                        'Date processed'    : time_start.strftime("%b %d %Y"),
                        'User'              : user_inputs.user_name,
                        'Data file'         : os.path.basename(csv_file_name)}
    # write everything to a html page
    html_file_name = htmltools.write_html_page( csv_file_name, apiless.CSV_type.unique_users, output_lists, 
                                                description_dict= description_dict, 
                                                statistics_info = stats_list, 
                                                page_title = f'List of {str(df_unique.shape[0])} unique users in {len(output_lists.notifications)} notifications',
                                                use_local_thumbnails = config.USE_LOCAL_THUMBNAIL, 
                                                ignore_columns = ['Avatar Href', 'Avatar Local', 'User Name', 'ID', 'Photo Thumbnail Href', 'Photo Thumbnail Local', 'Photo Link'],
                                                headline_tag='h4')
   # update the javascript used in the main html page to use the just created html result page
    utils.update_active_page_on_main_html_page_js(user_inputs.js_file_name, apiless.CSV_type.unique_users.name, os.path.basename(html_file_name))
    show_result_in_browser(user_inputs.main_html_page)
    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")
 
#---------------------------------------------------------------
def handle_option_8(driver, user_inputs, output_lists):
    """ Like n photos from a given user."""

    global logged_in
    time_start = datetime.datetime.now().replace(microsecond=0)
    printG(f"8. Starting auto-like {user_inputs.number_of_photos_to_be_liked} photo(s) of user {user_inputs.target_user_name}:")

    # if user provided password then login
    if user_inputs.password != '' and not logged_in:
        login(driver, user_inputs)
        if not logged_in:
            return
   
    # we dont want to load the homefeed page, nor to wait for it to complete, so we force a stop as soon as possible
    try:
        WebDriverWait(driver, timeout =  40).until(EC.presence_of_element_located((By.XPATH, '/html/body')))
        driver.execute_script("window.stop();") 
    except TimeoutException:
        pass #silently forget about it

    # do task   
    like_n_photos_from_user(driver, user_inputs.target_user_name, user_inputs.number_of_photos_to_be_liked, include_already_liked_photo_in_count=True, close_browser_on_error = False) 

    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")

#---------------------------------------------------------------
def handle_option_9(driver, user_inputs, output_lists):
    """Like n photos, starting at a given index, on various photo pages ."""

    global logged_in
    time_start = datetime.datetime.now().replace(microsecond=0)
    printG(f"9. Like {user_inputs.number_of_photos_to_be_liked} photo(s) from {user_inputs.gallery_name} gallery, start at index {user_inputs.index_of_start_photo + 1}:")
    
    # if user provided password then login
    if user_inputs.password != '' and not logged_in:
        login(driver, user_inputs)
        if not logged_in:
            return    
    driver.get(user_inputs.gallery_href)
    time.sleep(3)
    hide_banners(driver)

    # do task
    like_n_photos_on_current_page(driver, user_inputs.number_of_photos_to_be_liked, user_inputs.index_of_start_photo)

    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")

#---------------------------------------------------------------
def handle_option_10(driver, user_inputs, output_lists):
    """Like n photos of each user who likes a given photo or yours."""

    global logged_in
    time_start = datetime.datetime.now().replace(microsecond=0)
    printG(f"10. Like {user_inputs.number_of_photos_to_be_liked} photos of each user who liked the photo:")
    print(f'    Getting the list of users who liked the photo ...')
    # if user provided password then login
    if user_inputs.password != '' and not logged_in:
        login(driver, user_inputs)
        if not logged_in:
            return
    try:
        driver.get(user_inputs.photo_href)
    except:
        printR(f'    Invalid href: {user_inputs.photo_href}. Please retry.')
        show_menu(user_inputs)         
        return

    time.sleep(1)
    hide_banners(driver)        

    # do preliminary task: get the list of users who liked your given photo
    output_lists.like_actioners_list, _ = get_like_actioners_list(driver, user_inputs, output_lists)
    if len(output_lists.like_actioners_list) == 0: 
        printG(f'   - The photo {photo_tilte} has no affection')
        show_menu(user_inputs)
        return 
    actioners_count = len(output_lists.like_actioners_list)
    include_already_liked_photo_in_count = True  # meaning: if you want to autolike 3 first photos, and you found out two of them are already liked, then you need to like just one photo.
                                                    # if this is set to False, then you will find 3 available photos and Like them 

    # do main task
    for i, actor in enumerate(output_lists.like_actioners_list):  
        print_and_log(f'    User {str(i+1)}/{actioners_count}: {actor.display_name}, {actor.user_name}')
        # we may ignore so-called 'Deleted user' or 'Account inactive'
        #if 'anonymous_user_' in actor.user_name:
        #    printW(f'User {actor.user_name} no longer exist')
        #else:
        like_n_photos_from_user(driver, actor.user_name, user_inputs.number_of_photos_to_be_liked, include_already_liked_photo_in_count, close_browser_on_error=False)

    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")

#---------------------------------------------------------------
def handle_option_11(driver, user_inputs, output_lists):
    """Like n friend's photos in homefeed page."""
    
    global logged_in
    time_start = datetime.datetime.now().replace(microsecond=0)
    printG(f"11. Like {user_inputs.number_of_photos_to_be_liked} photos from the {user_inputs.user_name}'s home feed page:")
     # if user provided password then login
    if user_inputs.password != '' and not logged_in:
        login(driver, user_inputs)
        if not logged_in:
            return
    # make sure the current page is user's homefeed page 
    if 'https://500px.com/' not in driver.current_url :
        driver.get('https://500px.com')
        time.sleep(2)        
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

    # do task
    like_n_photos_on_homefeed_page(driver, user_inputs)     

    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")

#---------------------------------------------------------------
def handle_option_12(driver, user_inputs, output_lists):
    """Like n photos from each of m users in the last notifications.  """

    global logged_in
    time_start = datetime.datetime.now().replace(microsecond=0)
    printG(f"12. Like n photos from each of m users in the last notifications:")
    print(f'    - Getting the list of unique users in the last {user_inputs.number_of_notifications} notifications ...')
    # if user provided password then login
    if user_inputs.password != '' and not logged_in:
        login(driver, user_inputs)
        if not logged_in:
            return

    # we dont want to load the homefeed page, nor to wait for it to complete, so we force it to stop asap
    try:
        WebDriverWait(driver, timeout =  40).until(EC.presence_of_element_located((By.XPATH, '/html/body')))
        driver.execute_script("window.stop();") 
    except TimeoutException:
        pass # silently forget about this

    driver.get('https://500px.com/notifications')
    print('    - Getting notification list ...')
    time_out = 40
    try:
        WebDriverWait(driver, time_out).until(EC.presence_of_element_located((By.CLASS_NAME, 'notification_item')))
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    except TimeoutException:
        printR(f'Timed out {time_out}s loading the notifications list')

    hide_banners(driver)

    # get the pair of display name, user names of unique users in n notifications
    unique_names = get_notification_list(driver, user_inputs, output_lists, get_user_names_only=True)[1]

    # do main task
    users_count = len(unique_names)
    print(f"    Starting auto-like {user_inputs.number_of_photos_to_be_liked} photos of each of {users_count} users on the list ...")
    
    for i, item in enumerate(unique_names):
        name_pair = item.split(',')   # display name, user name
        if len(name_pair)==2:
            print(f'    User {str(i+1)}/{str(users_count)}: {name_pair[0]}')
            like_n_photos_from_user(driver, name_pair[1], user_inputs.number_of_photos_to_be_liked, include_already_liked_photo_in_count=True, close_browser_on_error=False)

    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")

#---------------------------------------------------------------
def handle_option_13(driver, user_inputs, output_lists):
    """ Play slideshow on a given gallery. """

    global logged_in
    time_start = datetime.datetime.now().replace(microsecond=0)
    printG("13. Playing the slideshow ...")
    print_and_log(f'    - Gallery: {user_inputs.gallery_name}, time interval: {user_inputs.time_interval}')
    # open a new Chrome Driver with specific options for playing the slideshow (we are not using the passed driver, which  may be in headless mode)
    chrome_options = Options()  
    chrome_options.add_argument('--kiosk')   
    chrome_options.add_argument('--hide-scrollbars')   
    chrome_options.add_argument('--disable-extensions')   
    # suppress popup 'Save Password'
    chrome_options.add_experimental_option("excludeSwitches", ['enable-automation', 'load-extension']);
    # suppress popup 'Disable Developer Mode Extension'
    chrome_options.add_experimental_option('prefs', {'credentials_enable_service': False, 'profile': {'password_manager_enabled': False}})
    
    driver_with_GUI = webdriver.Chrome(options=chrome_options)
    # login if credentials are provided
    if user_inputs.user_name and user_inputs.password and not logged_in:
        login(driver_with_GUI, user_inputs)
        if not logged_in:
            printR('   Error logging in. Slideshow will be played without a user login.')  

        # after a login, user's homefeed page will automatically loaded. We don't this page, nor to waste time waiting for it to complete, 
        # so we force a hard stop asap
        try:
            WebDriverWait(driver_with_GUI, timeout =  40).until(EC.presence_of_element_located((By.XPATH, '/html/body')))
            driver.execute_script("window.stop();") 
        except TimeoutException:
            pass # silently forget about this

    # then we load the desised gallery    
    driver_with_GUI.get(user_inputs.gallery_href)
    time.sleep(2)

    # one ugly way to wait for the gallery to load, while all other 'legit 'ways do not seem to work
    scroll_height = driver_with_GUI.execute_script("return document.documentElement.scrollHeight")
    while scroll_height and scroll_height < 1800:
        time.sleep(1)
        scroll_height = driver_with_GUI.execute_script("return document.documentElement.scrollHeight")

    time_out = 120
    try:
        WebDriverWait(driver_with_GUI, time_out).until( EC.presence_of_element_located((By.CLASS_NAME, 'finished')) )
    except  TimeoutException:
         printR(f'   Time out ({time_out}s! Error loading galleries.')
         return

    hide_banners(driver_with_GUI)

    # do task
    play_slideshow(driver_with_GUI, int(user_inputs.time_interval))
    
    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")
    webtools.close_chrome_browser(driver_with_GUI)

#---------------------------------------------------------------
# EXTRA OPTIONS, not yet available from the menu, in progress, experimental...
def handle_option_99(driver, user_inputs, output_lists):
    """Check/Update following statused of people you are following.
    
    This function checks all users that you are following, to see whether they are following you or not.
    If you already have a following list on  disk, this will offer you to update the file, instead of doing everything from scratch.
    Note: this is a time-cosumming process. Use it responsibly and respectfully 
    """

    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.replace(microsecond=0).strftime(config.DATE_FORMAT)
    if user_inputs.number_of_users == -1:
        message = f'99. Get the following statuses of all users that {user_inputs.user_name} is following:'
    else:
        message = f'99. Get the following statuses of {user_inputs.number_of_users} users, starting from index {user_inputs.index_of_start_user + 1}:'
    printG(message)
    
    csv_file = ''
    # Provide option whether to use the last Followings list on disk or to start from scratch
    following_file = utils.get_latest_file(output_lists.output_dir, user_inputs.user_name, apiless.CSV_type.followings, file_extenstion = 'csv')
    if following_file != '':
        print('    Existing Followings list on disk:')
        printY(f"{following_file}", write_log=False)
        sel = input("Using this file? (y/n) > ")
        # use the existing followings list
        if sel =='y':
            csv_file = following_file
        # redo the followings list:        
        else:
            printG(f"99. Getting {user_inputs.user_name}'s Followings list ...")
            output_lists.followings_list = get_followings_list(driver, user_inputs, output_lists)
            # write result to csv
            if len(output_lists.followings_list) == 0:
                printR(f'    User {user_inputs.user_name} does not follow anyone or error on getting the followings list')
                return ''
            csv_file = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{len(output_lists.followings_list)}_followings_{date_string}.csv')
            if utils.write_users_list_to_csv(output_lists.followings_list, csv_file) == False:
                printR(f'    Error writing the output file\n:{csv_file}')
                return ''
    # do task
    get_following_statuses(driver, user_inputs, output_lists, csv_file )

    # write main items in csv file and everything else to the result html page  
    html_file_name = htmltools.write_html_page( csv_file, apiless.CSV_type.followings, output_lists, 
                                                description_dict = description_dict, 
                                                page_title = f'List of {str(len(output_lists.followings_list ))} followings',
                                                use_local_thumbnails = config.USE_LOCAL_THUMBNAIL, 
                                                ignore_columns = ['Avatar Href', 'Avatar Local', 'User Name', 'ID', 'Relationship'], 
                                                headline_tag='h4')


    # update the javascript used in the main html page to use the just created html result page
    utils.update_active_page_on_main_html_page_js(user_inputs.js_file_name, apiless.CSV_type.followings.name, os.path.basename(html_file_name))
    show_result_in_browser(user_inputs.main_html_page)

    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")

#---------------------------------------------------------------
# EXTRA OPTIONS, not yet available from the menu, in progress, experimental...
def handle_option_98(driver, user_inputs, output_lists, sort_column_header='No', ascending=True):
    """Like n photos of m users from a given csv files. 

    - The given csv file is supposed to have a header row, with at least one column named 'User Name'.
      All the csv files produced by this program, except the photo list file, satisfy this requirement and can be used.
    - There is an option to process part of the list, by specifying the start index and the number of users   
    - There is also option to sort a selectable column in the csv file before processing 
    """
    global logged_in
    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.replace(microsecond=0).strftime(config.DATE_FORMAT)
    printG("98. Like n photos of m users from a given csv files:")

    # do main task
    dframe = pd.read_csv(user_inputs.csv_file, encoding='utf-16')  
    # validate the given  csv file
    if len(list(dframe)) == 0 or not 'User Name' in list(dframe):
        printR(f'   The given csv file is not valid. It should  have a header row with  at leat one column named "User Name":.\n\t{user_inputs.csv_file}')
        return

    printG(f"98. Like {user_inputs.number_of_photos_to_be_liked} photos from {user_inputs.number_of_users} users, starting from index {user_inputs.index_of_start_user} from the file:")
    printG('   - ' + {user_inputs.csv_file}, write_log=False)    
    print(f'    There are {dframe.shape[1]} columns:')
    printG(list(dframe), write_log=False)
    sort_header = input('Enter the desired sort column >')
    if not sort_header:
        sort_header = "No" 
    sort_ascending = True
    ans = input('Sort descending ?(y/n) >')
    if ans == 'y':
        sort_ascending = False
    df = dframe.sort_values(sort_header, ascending = sort_ascending )   
    
    # if user provided password then login
    if user_inputs.password != '' and not logged_in:
        login(driver, user_inputs)
        if not logged_in:
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

        like_n_photos_from_user(driver, user_inputs.target_user_name, user_inputs.number_of_photos_to_be_liked, include_already_liked_photo_in_count=True, close_browser_on_error = False)

    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")

#---------------------------------------------------------------
def handle_option_14(driver, user_inputs, output_lists):
    """Create and/or update local database based on the latest csv files on disk
       - if database does not exist, create it.
       - search the output directory for the latest csv files: photos, followers, followings, notifications list
       - create/update the tables, ignoring duplicated records
    """
    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.replace(microsecond=0).strftime(config.DATE_FORMAT)
    
    # connect to database (create it if it does not exist)
    if not os.path.isfile(user_inputs.db_path):
        option = "Create local database based on the latest csv files on disk"
    else:
        option = "Update local database based on the latest csv files on disk"
    printG(f'14. {option}:')
 
    db_connection = sqlite3.connect(user_inputs.db_path)
    db.create_if_not_exists_photos_table(db_connection)
    db.create_if_not_exists_followers_and_followings_tables(db_connection)
    db.create_if_not_exists_notifications_tables(db_connection)
    
    types_to_process = [apiless.CSV_type.photos_public, apiless.CSV_type.notifications, apiless.CSV_type.followers, apiless.CSV_type.followings]
    records_changed_sofar = 0
    for csv_type in types_to_process:
        records_changed_sofar, recent_changes, csv_file =  db.insert_latest_csv_data_to_database(db_connection, 
                                                                                                 config.OUTPUT_PATH, 
                                                                                                 records_changed_sofar, 
                                                                                                 user_inputs.user_name, 
                                                                                                 csv_type)
    db_connection.close()
    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")

#--------------------------------------------------------------
def handle_option_15(driver, user_inputs, output_lists):
    """ Data analysis: categorize users according to the following statuses, based on two latest csv files on disk: the followers and followings lists.
        If these files do not exist, or if they exist but the user wants to re-extract the lists, then there is option to do so. 
        The results are 4 pairs of csv and html files: 
            - List of reciprocal following users
            - List of users who followed you but you do not follow them
            - List of users you followed but they do not follow you
            - List of all users combined """

    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.strftime(config.DATE_FORMAT)
    option = "15. Categorizing users based on the followers and followings lists:"
    printG(option)
    use_followers_file_on_disk, use_followings_file_on_disk = 'n', 'n'
    # Provide option whether to use the last followers csv file on disk or to start from scratch
    followers_file = utils.get_latest_file(output_lists.output_dir, user_inputs.user_name, apiless.CSV_type.followers, file_extenstion = 'csv')
    if followers_file != '':
        use_followers_file_on_disk = input("Using this file? (y/n) > ")

    # Provide option whether to use the last following csv file on disk or to start from scratch
    followings_file = utils.get_latest_file(output_lists.output_dir, user_inputs.user_name, apiless.CSV_type.followings, file_extenstion = 'csv')
    if followings_file != '':
        use_followings_file_on_disk = input("Using this file? (y/n) > ")
    
    # Extract followers list from 500px server in case the user does not want to use the existing files
    if use_followers_file_on_disk == 'n':
        print(f"    Getting {user_inputs.user_name}'s Followers list ...")
        output_lists.followers_list = get_followers_list(driver, user_inputs, output_lists)
        if len(output_lists.followers_list) == 0:
            printR(f'   - Error getting the followers list.')

        # write result to csv
        if len(output_lists.followers_list) == 0:
            printR(f'    User {user_inputs.user_name} does not follow anyone or error on getting the followings list')
            return ''
        file_name = f'{user_inputs.user_name}_{len(output_lists.followers_list)}_followers_{date_string}.csv'
        followers_file = os.path.join(output_lists.output_dir, file_name)
        if utils.write_users_list_to_csv(output_lists.followers_list, followers_file) == False:
            printR(f'    Error writing the output file\n:{followers_file}')
            return ''
        description_dict = {'Option 15'     : '<b>Categorize users based on theirs following statuses', 
                            'Date processed': time_start.strftime("%b %d %Y"),
                            'User'          : user_inputs.user_name, 
                            'Data file'     : file_name}
  
        # write main items in csv file and everything else to the result html page  
        html_file_name = htmltools.write_html_page( followers_file, apiless.CSV_type.followers, output_lists, 
                                                    description_dict = description_dict, 
                                                    page_title = f'List of {str(len(output_lists.followers_list ))} followers' ,
                                                    use_local_thumbnails = config.USE_LOCAL_THUMBNAIL, 
                                                    ignore_columns = ['Avatar Href', 'Avatar Local', 'User Name', 'ID', 'Relationship'], 
                                                    headline_tag='h4')


    # close the popup windows, if they are opened from previous task
    webtools.close_popup_windows(driver, close_ele_class_names = ['close', 'ant-modal-close-x'])

    # Extract followings list from 500px server in case the user does not want to use the existing files
    if use_followings_file_on_disk == 'n':
        print(f"    Getting {user_inputs.user_name}'s Followings list ...")
        output_lists.followings_list = get_followings_list(driver, user_inputs, output_lists)
        if len(output_lists.followings_list) == 0:
            printR(f'   - Error getting the followings list.')
            return
        # write result to csv
        if len(output_lists.followings_list) == 0:
            printR(f'    User {user_inputs.user_name} does not follow anyone or error on getting the followings list')
            return ''
        followings_file = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{len(output_lists.followings_list)}_followings_{date_string}.csv')
        if utils.write_users_list_to_csv(output_lists.followings_list, followings_file) == False:
            printR(f'    Error writing the output file\n:{followings_file}')
            return ''
        description_dict = {'Option 15'     : '<b>Categorize users based on theirs following statuses', 
                            'Date processed': date_string, 
                            'User'          : user_inputs.user_name,
                            'Data file'     : os.path.basename(followings_file)}
        ## write result to html
        #htmltools.CSV_to_HTML(followings_file, apiless.CSV_type.followings, output_lists, use_local_thumbnails = config.USE_LOCAL_THUMBNAIL, 
        #            ignore_columns = ['Avatar Href', 'Avatar Local', 'User Name', 'ID', 'Relationship'], desc_dict = description_dict)

        # write main items in csv file and everything else to the result html page  
        html_file_name = htmltools.write_html_page( followings_file, apiless.CSV_type.followings, output_lists, 
                                                    description_dict = description_dict, 
                                                    page_title = f'List of {str(len(output_lists.followings_list ))} followings',
                                                    use_local_thumbnails = config.USE_LOCAL_THUMBNAIL, 
                                                    ignore_columns = ['Avatar Href', 'Avatar Local', 'User Name', 'ID', 'Relationship'], 
                                                    headline_tag='h4')

    
    # main task
    # create followers dataframe
    df_followers= utils.CSV_file_to_dataframe(followers_file)

    # create followings dataframe
    df_followings = utils.CSV_file_to_dataframe(followings_file)

    # merge followers and followings dataframes, preserving all data 
    df_m = pd.merge(df_followers, df_followings, how='outer', indicator = True,  suffixes=('_follower_order', '_following_order'), 
                      on=['Avatar Href', 'Avatar Local', 'Display Name', 'ID', 'Followers Count', 'Relationship', 'User Name'] ) 
    
    # drop the column 'Relationship'. We will use the merged column instead
    df_m.drop(['Relationship'], axis=1, inplace=True)
    
    # removed the combined values in the overlap columns after merging
    # I'm using pandas 1.0.1 and yet to figure out how to avoid this: different values of the same column name are combined with a dot in between, eg 23.5, 
    # even they are already separate by two extra columns _x and _y. So, for now, we manually remove the extra part
    df_m['No_follower_order']   = df_m['No_follower_order'].apply(lambda x: '' if math.isnan(x) else str(x).split('.')[0])
    df_m['No_following_order'] = df_m['No_following_order'].apply(lambda x: '' if math.isnan(x) else str(x).split('.')[0])
    
    # change the merged values to meaningful text. (Note: unseen column '_merge' needs to have new values added to its category, before we can change the values) 
    df_m._merge = df_m._merge.cat.add_categories(['Reciprocal', 'Not Follow', 'Following'])    
    df_m.loc[df_m._merge == 'both','_merge']      = 'Reciprocal'
    df_m.loc[df_m._merge == 'left_only','_merge'] = 'Not Follow'
    df_m.loc[df_m._merge == 'right_only','_merge']= 'Following'

    # renamed some columns
    df_all = df_m.rename(columns={'No_follower_order': 'Follower Order', 'No_following_order': 'Following Order', '_merge': 'Relationship'})

    # Reciprocal following: users who follow you and you follow them 
    df_reciprocal = df_all[df_all['Relationship'] == 'Reciprocal']

    # Not Follow: users who follow you but you do not follow them
    df_not_follow =  df_all[df_all['Relationship'] == 'Not Follow']

    # Following: users who you are following but they do not follow you
    df_right_only =  df_all[df_all['Relationship'] == 'Following']                                               # getting the names
    df_not_follower = pd.merge(df_followings, df_right_only[['User Name']], how='inner', on='User Name')         # from names, getting the detail info (a whole row on other table) 
    df_not_follower = df_not_follower.rename(columns={'No': 'Following Order', 'Followers': 'Followers Count'})  # renaming some columns
    df_not_follower['Follower Order'] = ''                                                                       # add missing column with empty values
    df_not_follower['Relationship'] = 'Following'                                                                # put in the value 

    # write dataframe to csv, html. Show html
    df_to_process = [df_reciprocal, df_not_follow, df_not_follower, df_all]
    csv_type_to_process= [apiless.CSV_type.reciprocal, apiless.CSV_type.not_follow, apiless.CSV_type.following, apiless.CSV_type.all_users]
    print_and_log(f'   - Analyzing users relationships')
    #pd.options.mode.chained_assignment = None # this bypass the pandas' SettingWithCopyWarning, which we don't care because we are going to throw way the  copies
    stats_dict = {}
 
    for df, csv_type in zip(df_to_process, csv_type_to_process):
        file_title = ''
        # add an index column, started at 1
        df['No'] = range(1, len(df) + 1)

        # Reorder columns to make it easier to generate html file . This is original order:
        # Follower Order, Avatar Href, Avatar Local, Display Name, User Name, ID, Followers Count, Relationship, Following Order, Relationship, No
        new_columns_order = ['No', 'Avatar Href', 'Avatar Local', 'Display Name', 'User Name', 'ID', 'Followers Count', 'Follower Order', 'Following Order', 'Relationship', ]
        df = df[new_columns_order]

        ignore_columns = ['Avatar Href', 'Avatar Local', 'User Name', 'ID']
        table_width = '900px'
        # create a statistics list to show on the result html page 
        if csv_type == apiless.CSV_type.not_follow:
            ignore_columns.extend(['Following Order'])
            option_key = 'Option 15 (2 of 4)'
            option = "Categorizing users based on the followers and followings lists"
            file_title = f'List of {str(df.shape[0])} followers that you do not follow'
            stats_list = [['not_follow', 'Not Follow', str(df_not_follow.shape[0]), 'You do not follow your follower']]
        elif csv_type == apiless.CSV_type.following:
            option_key = 'Option 15 (3 of 4)'
            option = "Categorizing users based on the followers and followings lists"
            ignore_columns.extend(['Follower Order'])
            file_title = f'List of {str(df.shape[0])} users that you follow'
            stats_list = [['following', 'Following', str(df_not_follower.shape[0]), 'You are following this user without being followed back']]
        elif csv_type == apiless.CSV_type.reciprocal:
            option_key = 'Option 15 (1 of 4)'
            option = "Categorizing users based on the followers and followings lists"
            file_title = f'List of {str(df.shape[0])} reciprocal users'
            stats_list = [['reciprocal', 'Reciprocal Following', str(df_reciprocal.shape[0]), 'You and this user follow each other']]
                          
        elif csv_type == apiless.CSV_type.all_users:
            option_key = 'Option 15 (4 of 4)'
            option = "Categorizing users based on the followers and followings lists"
            file_title = f'List of {str(df.shape[0])} users with their following statuses'
            stats_list = [['reciprocal',      'Reciprocal Following',  str(df_reciprocal.shape[0]),      'You and this user follow each other'],
                          ['not_follow',      'Not Follow',            str(df_not_follow.shape[0]),        'You do not follow your follower'],
                          ['following',       'Following',             str(df_not_follower.shape[0]),       'You are following this user without being followed back']]
        
        stats_list.append(['Follower Order',  'The reverse chronological order at which a user followed you']) 
        stats_list.append(['Following Order', 'The reverse chronological order at which you followed a user'])

        file_name = f'{user_inputs.user_name}_{len(df)}_{csv_type.name}_{date_string}.csv'
        csv_file_name = os.path.join(output_lists.output_dir, file_name)  
        printG(f'   - {csv_type.name.upper()}: ./Output/{file_name}')
        df.to_csv(csv_file_name, encoding='utf-16', index = False)
        description_dict = {f'{option_key}'   : f'<b>{option}', 
                             'Date processed' : time_start.strftime("%b %d %Y"),
                             'User'           : user_inputs.user_name, 
                             'Data file'      : file_name}

        # write everything to a html page
        html_file_name = htmltools.write_html_page( csv_file_name, csv_type, output_lists, 
                                                    description_dict= description_dict, 
                                                    statistics_info = stats_list, 
                                                    page_title = file_title,
                                                    use_local_thumbnails = config.USE_LOCAL_THUMBNAIL, 
                                                    ignore_columns = ignore_columns, 
                                                    headline_tag='h4')
        # update the javascript used in the main html page to use the just created html result page
        utils.update_active_page_on_main_html_page_js(user_inputs.js_file_name, csv_type.name, os.path.basename(html_file_name))
        show_result_in_browser(user_inputs.main_html_page)

    printG(f'   Duration {datetime.datetime.now().replace(microsecond=0) - time_start}s') 

#-------------------------------------------------------------
def handle_option_16(driver, user_inputs, output_lists):
    """ - Read all notifications from local database
        - Count the number of occurences of each user on the list
        - Compile a list of unique users with occurences counts, last action date, numbers of liked, followed, commennted and added to gallery 
        - Save the list to csv file. Create the html file and show.
    """

    time_start = datetime.datetime.now().replace(microsecond=0)
    date_string = time_start.replace(microsecond=0).strftime(config.DATE_FORMAT)
    printG("16. Notifications analysis ...")
    # update database
    records_changed = db.insert_all_notification_csv_files_to_database(user_inputs.db_path, config.OUTPUT_PATH, user_inputs.user_name)
    if records_changed == 0:
        print_and_log('No records changed')
        return

    # Task 1 of 2: All notifications: read from database, write to csv, html and show html
    conn = sqlite3.connect(user_inputs.db_path)  
    df_notif = pd.read_sql_query("SELECT * FROM notifications", conn)   
    df_notif.sort_values(by=['Time Stamp'], ascending=False, inplace=True)
    file_name = f'{user_inputs.user_name}_all_notifications_({str(df_notif.shape[0])})_{date_string}'
    csv_file_name =  os.path.join(output_lists.output_dir, f'{file_name}.csv')

    ## gather statistics 
    stats_dict = utils.get_notifications_statistics(df_notif)
 
    # description 
    description_dict = {'Option 16 (1of2)'  : f'<b>Notification analysis: All recorded notifications from database', 
                        'Date processed'    : time_start.strftime("%b %d %Y"),
                        'User'              : user_inputs.user_name,  'Data file': f'{file_name}.csv',
                        'Following'         : '<i>You are following your new follower',
                        'Not Follow'        : '<i>You do not follow your new follower'}
    # write notification objects list to csv 
    df_notif.to_csv(csv_file_name, encoding='utf-16', index = False)   

    # write everything to html
    html_file_name = htmltools.write_html_page( csv_file_name, apiless.CSV_type.all_notifications, output_lists, 
                                                description_dict= description_dict, 
                                                statistics_info = stats_dict, 
                                                page_title = f'List of all {str(df_notif.shape[0])} recorded notifications from local database',
                                                photos_html_string = '',  
                                                use_local_thumbnails = config.USE_LOCAL_THUMBNAIL, 
                                                ignore_columns=['Avatar Href', 'Avatar Local', 'User Name', 'ID', 'Photo Thumbnail Href', 'Photo Thumbnail Local', 'Photo Link'], 
                                                headline_tag='h4')
   # update the javascript used in the main html page to use the just created html result page
    utils.update_active_page_on_main_html_page_js(user_inputs.js_file_name, apiless.CSV_type.all_notifications.name, os.path.basename(html_file_name))
    show_result_in_browser(user_inputs.main_html_page)

    conn.close()

    # Task 2 of 2: Process unique users list with detailed analysis, write to csv, html and show html 
    df_unique, stats_list = process_unique_users(df_notif, user_inputs.user_name, output_lists.output_dir)
    
    # write the result to csv file
    csv_file_name  = os.path.join(config.OUTPUT_PATH,  
                f"{user_inputs.user_name}_all_unique_users_({str(df_unique.shape[0])})_in_all_{df_notif.shape[0]}_notifications_{date_string}.csv")
    df_unique.to_csv(csv_file_name, encoding='utf-16', index = False)

    description_dict = {'Option 16 (2of2)' : '<b>Notification analysis: extract unique users and theirs statistics',  
                        'Date processed'    : time_start.strftime("%b %d %Y"),
                        'User'              : user_inputs.user_name,
                        'Title'             : f'{str(df_unique.shape[0])} unique users in {df_notif.shape[0]} recorded notifications',
                        'Data file'         : os.path.basename(csv_file_name)}

    # write everything to an html page
    html_file_name = htmltools.write_html_page( csv_file_name, apiless.CSV_type.all_unique_users, output_lists, 
                                                description_dict= description_dict, 
                                                statistics_info = stats_list, 
                                                page_title = f'All {str(df_unique.shape[0])} unique users in {df_notif.shape[0]} recorded notifications', 
                                                use_local_thumbnails = config.USE_LOCAL_THUMBNAIL, 
                                                ignore_columns=['Avatar Href', 'Avatar Local', 'User Name', 'ID'], 
                                                headline_tag='h4')
   # update the javascript used in the main html page to use the just created html result page
    utils.update_active_page_on_main_html_page_js(user_inputs.js_file_name, apiless.CSV_type.all_unique_users.name, os.path.basename(html_file_name))
    show_result_in_browser(user_inputs.main_html_page)

    printG(f"   Duration: {datetime.datetime.now().replace(microsecond=0) - time_start}s")
        
#--------------------------------------------------------------
def process_unique_users(df_notif, user_name, output_dir):
    """ Given a notifications dataframe, extract the unique users and theirs statistics info from it. 
        Return a uniques users dataframe with the theirs analysis data, and a 2D list of strings that will be used for a summary html table
        
        Statistics data for each user are: 
        Last Action Date, Actions count, Liked count, Followed count, Commented count , Added-To-Gallery count, and Relationship
        Relationship is one in for types: Reciprocal Following, Followed You, You Follow, and No relationship 
        We use the csv file, if existed, created in option 15: "Categorize users based on following statuses" to get the relationship status. """

    if df_notif.shape[0] == 0:
        print_and_log('    - No notifications provided')
        return ''

    pd.options.mode.chained_assignment = None

    df_unique = utils.analyze_notifications(df_notif)  
 
    # find the latest all_users csv file on disk
    all_users_file = utils.get_latest_file(output_dir, user_name, apiless.CSV_type.all_users, file_extenstion = 'csv')

    # no users analysis file (i.e step 15: Categorize users based on following statuses was not done
    stats_list = []
    if all_users_file == '':   
        # sort table by the Actions Counts
        print_and_log('    - No analysis data for a complete report. Consider doing option 15 prior to this. Now processing the basic analysis.  ')
        df_unique.sort_values(by=['Actions Count'], ascending=False, inplace=True)
        return df_unique, stats_list        

    # we have the list of users relationships, we will use it to update the relationships in the unique users list 
    else:   
        print_and_log(f'    - Use data analysis from file: {all_users_file}')
        df_all_users = utils.CSV_file_to_dataframe(all_users_file)
        df_merge, stats_list = utils.merge_relationships(df_unique, df_all_users)
        return df_merge, stats_list        

#--------------------------------------------------------------
def process_photo_group(driver, user_inputs, output_lists, group_href, date_string, csv_type, use_local_thumbnails = True ):
    """ Given the link to a photo group page(public, unlisted or limited access):
            1) Extract all the photos on the page, scrolling down if needed, create a list of photo objects
            2) Save photos list to a csv file 
            3) Convert the photos list to an html table 
        Return photos list, csv_file_name, html_table_object """

    photos_list= []
    photos_html_string = None 
    csv_file_name = ''

    # if user is not logged in, we process only the public photos, which are located on the user photo home page 
    if user_inputs.user_name in group_href:
        photos_list, error_message = get_not_logged_in_user_photos_list(driver, user_inputs, output_lists, group_href)
    else: 
        photos_list, error_message = get_managed_photos_list(driver, user_inputs, output_lists, group_href)

    if error_message:
        printR('   - ' + error_message)
    else:
        if photos_list and len(photos_list) > 0:
            csv_file_name = os.path.join(output_lists.output_dir, f'{user_inputs.user_name}_{len(photos_list)}_{csv_type.name}_{date_string}.csv')    
            # write photos list to csv
            if not utils.write_photos_list_to_csv(user_inputs.user_name, photos_list, csv_file_name):
                printR(f'   Error writing the output file\n:{csv_file_name}')
                csv_file_name = ''
            else:
                photos_html_string = htmltools.CSV_photos_list_to_HTML_table(csv_file_name, csv_type, output_lists, use_local_thumbnails, 
                                ignore_columns = ['ID', 'Author Name', 'Href', 'Thumbnail Href', 'Thumbnail Local', 'Rating'], headline_tag='h4' )
    return photos_list, csv_file_name, photos_html_string

#--------------------------------------------------------------
def create_top_photos_and_statistics(user_name, photos_list):
    """ Given a list of photos;
        - extract the top photos and write them to a csv file
        - create dictionary for summary, or overview of the photos 
       Return the csv file name or an empty string if no file was written"""

 
    # create dataframe from list of photo objects
    top_photos_html_string = ''
    df = pd.DataFrame.from_records([item.to_dict() for item in photos_list]) 
    if df.shape[0] == 0:
        return '' 

    # get indexes of top photos 
    maxPulse_index      = df['Highest Pulse'].astype(float).argmax()
    maxViews_index      = df['Views'].astype(int).argmax()
    maxLikes_index      = df['Likes'].astype(int).argmax()
    maxComments_index   = df['Comments'].astype(int).argmax()
    max_galleries_index = df['Galleries'].astype(int).argmax()

    # create the top-photos dataframe, merge duplicate photos 
    df2 = df.iloc[[maxPulse_index, maxViews_index, maxLikes_index, maxComments_index, max_galleries_index ],:]
    df3 = utils.merge_duplicate_top_photos(df2)

    # write top photos dataframe to csv file
    csv_top_photos_file_name =  os.path.join(config.OUTPUT_PATH, f'{user_name}_top_photos.csv')
    df3.to_csv(csv_top_photos_file_name, encoding='utf-16', index = False)
  
    # create  statistics table
    # ref: No,Author Name,ID,Photo Title,Href,Thumbnail Href,Thumbnail Local,Views,Likes,Comments, Galleries, Highest Pulse,Rating, Date, Category, Featured In Galleries, Tags      
    # get some statistics:
    total_views = df['Views'].sum()
    total_likes = df['Likes'].sum()
    total_comments = df['Comments'].sum()
    last_upload_date   = df['Date'].iloc[[0]].values[0]
    first_upload_date = df['Date'].iloc[[-1]].values[0]                
    try:
        last_date_obj = datetime.datetime.strptime(last_upload_date, "%Y %m %d").date()
        first_date_obj = datetime.datetime.strptime(first_upload_date, "%Y %m %d").date()
        days = (last_date_obj -first_date_obj).days
        last_date  = last_date_obj.strftime("%b %d %Y")
        first_date = first_date_obj.strftime("%b %d %Y")
    except:
        printR(f'Error converting datetime string:{last_upload_date}, {first_upload_date}')
        last_date = last_upload_date
        first_date = first_upload_date
        days = ''
    stats_dict = {'Last Upload Date': last_date, 'First Upload Date': first_date, 'Duration': f'{days} days', 
                    'Total Views' : total_views, 'Total Likes': total_likes, 'Total Comments': total_comments}


    return csv_top_photos_file_name, stats_dict  

#--------------------------------------------------------------
def main():
    global logged_in
    global web_browser_for_result
    web_browser_for_result = None

    os.system('color')
    driver = None   
 
    logger.info('Started: =====================================')
    print_and_log(f'Script path: {os.path.dirname(sys.argv[0])}')
    print_and_log(f'Output path: {config.OUTPUT_PATH}')
    print_and_log(f'Log file:    {config.LOG_FILE}')

    desired_capab = DesiredCapabilities.CHROME
    desired_capab["pageLoadStrategy"] = "none"

    # chrome driver takes a few seconds to load, so we let a thread to handle it while we go on with the menu and user inputs. 
    my_queue = queue.Queue()
    th = Thread(target = webtools.start_chrome_browser, args=([], config.HEADLESS_MODE, desired_capab, my_queue) )
    th.start()

    # bypass the pandas' SettingWithCopyWarning, which we don't care because we are going to throw way the  copies
    pd.options.mode.chained_assignment = None 

    # check internet and 500px server connections, if needed  
    #if not webtools.has_server_connection(driver, r'https://500px.com'):
    #    return   

    #declare a dictionary so that functions can be referred to from a string of digit(s)
    Functions_dictionary = {   
            "1" : handle_option_1, 
            "2" : handle_option_2, 
            "3" : handle_option_3,
            "4" : handle_option_4, 
            "5" : handle_option_5, 
            "6" : handle_option_6, 
            "7" : handle_option_7, 
            "8" : handle_option_8, 
            "9" : handle_option_9, 
            "10": handle_option_10, 
            "11": handle_option_11,
            "12": handle_option_12, 
            "13": handle_option_13,  
            "14": handle_option_14,
            "15": handle_option_15,
            "16": handle_option_16,

            # options not yet available from the menu
            "99": handle_option_99,
            "98": handle_option_98,
            }

    output_lists = apiless.OutputData()
    
    user_inputs = define_and_read_command_line_arguments()
    if  user_inputs.use_command_line_args == False:
        show_menu(user_inputs)  

    while user_inputs.choice != 'q':
        #restart for different user
        if user_inputs.choice == 'r': 
            user_inputs.Reset()
            output_lists.Reset()
            logged_in = False
            # close and start a new web driver
            webtools.close_chrome_browser(driver)
            driver = None
            th = Thread(target = webtools.start_chrome_browser, args=([], config.HEADLESS_MODE, desired_capab, my_queue) )
            th.start()
            
            user_inputs = define_and_read_command_line_arguments()
            show_menu(user_inputs, 'Restarted for a different user.')
            continue
        else:
        # add user to enter additional inputs according to the selected options
            if not user_inputs.use_command_line_args and int(user_inputs.choice) >= 5:
                if get_additional_user_inputs(user_inputs) == False:
                    continue

            # make sure the driver is ready 
            while driver == None:
                driver = my_queue.get()     

            # dynamically call the function to perform the task 
            Functions_dictionary[user_inputs.choice](driver, user_inputs, output_lists)

            # close the popup windows, if they are opened from previous task
            webtools.close_popup_windows(driver, close_ele_class_names = ['close', 'ant-modal-close-x'])

        # after finishing a task, if we are in the command-line mode, we are done, since the specific task has finished 
        if  user_inputs.use_command_line_args:
            sys.exit()
             
        # if not, show the menu for another task selection  
        else:
            input("Press ENTER to continue")
            show_menu(user_inputs)
            continue

    webtools.close_chrome_browser(driver)
    #webtools.close_chrome_browser(web_browser_for_result)
    logged_in = False

#---------------------------------------------------------------
if __name__== "__main__":
    main()

