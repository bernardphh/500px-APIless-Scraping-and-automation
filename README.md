```diff
+ Please notice that this project is no longer updated since January 2021. Some, if not all, functionalities may stop working. 
```
# 500px-APIless: Scraping and automation
A personal project created by curiosity and for fun, to extract information from 500px web site for data analyzing, and to perform some automated processes.

<br/>

## A BIT OF HISTORY: ##

[500px](https://500px.com) is a famous photo sharing site who recently shutdown its API access (June 24 2018), leaving numerous applications relied on its API, useless.

Without the API, data is harder to collect, and it takes longer time to get them.

But gone the API, arrived the challenges!


As a 500px user who does not want to be manipulated by bots, Initially I just wanted to gather data from the site, manually analyze it and figure it out the users who: 
 - Like every photo I posted, give un-mistaken robot comments, and like my photo back every time I liked theirs
 - Get unbelievable number of followers
 - Follow me then un-follow me if I don't follow them back. 
 - Follow me but do not have any interaction   ...
 
And as a programmer, I got curious, wondering how things can be done. I ended up creating some bots myself.

For testing, I created a dummy account. 
The photographer side of mine tells me: Don't get fool yourself by the "artifical" number of affections. It could be manipulated if one chooses to do so.
The programmer side, on the other hand, says: Why not? you got played. 

At the end of the day, I truly believe that using bots to promote popularity will do you harm. It kills all the fun interacting with 'human' fellow photographers.

Unless, you are in it not for fun, or your fun is getting ahead, no matter what...

Before trying my bots- just for fun, you may say- check out this old but very interesting article I came across some time ago. 
It is from  Andy Hutchinson and it pretty much said it all:
 [The Real Reason You Suck on Photo Sharing Sites: The Bots are Beating You](https://petapixel.com/2017/02/27/real-reason-suck-photo-sharing-sites-bots-beating/) 

<br/>

## WHAT IT CAN DO SO FAR: ##

![Main menu](Snapshots/MainMenu.png)

The program has four main functionalities:

### DATA COLLECTION <br/>
The first 7 options are for data collection. The results of these tasks are saved on disk in CSV and HTML formats. 
CSV files are used for statistical analysis, and for the automated processes. 
HTML files are used for presentation, they are automatically shown after a data collection task is completed. 
They are also served as a tool to sort, filter or search the data


### AUTOMATED PROCESSES <br/>
The options 8 to 12 are the automated processes, robots, or bots, that will perform some actions.

### ENTERTAINMENT <br/>
Option 13 allows you to play the slideshow of photos from preselected or customized galleries

### DATA ANALYSIS <br/>
To falicitate the analysis tasks, we create a local SQLite database using the csv files obtained in the data collection processes.<br/>
We have the analysis for photos, users, and notifications:<br/><br/>
Photos:<br/> 
-	List of top photos in terms of Highest Pulse, Views, Likes, Comments, and Featured Galleries <br/>
-	List of all photos with the detail info arranged in columns, where you can sort, filter, or search<br/>
<br/>
<br/>
Followers and followings users are categorized into 3 groups: <br/>
   -	Followers that you are also following <br/>
   -	Followers that you do not follow <br/>
   - Users that you  are following but they do not follow you. <br/>
<br/>
<br/>
Notifications collected bit by bit over times are combined together into one  table in database, which is used for creating statistics such as: <br/>
  - All unique users  that had interactions with your photos <br/>
  - For each user, the total number the interactions, total numbers of likes, comments, and featuring your photos <br/>
  - The following status between you and each user <br/>
<br/>
<br/>

For a demo of this data collection & analysis results, see [main-html-page_demo.gif](https://github.com/bernardphh/500px-APIless/blob/master/main-html-page_demo.gif), or go to the end of this page.


## ENVIRONMENT: ##

This was developed using Visual Studio Code, testing and run on Windows 10, Python version 3.6

<br/>

## DEPENDENCIES: ##

Python 3.6 or later 

Selenium, Pandas and ChromeDriver

<br/>

## USAGE FOR WINDOW OS: ##

Extract all to a location on disk, say "Download folder". You should have this folders structure: 
<br/>
<p align="center">
<img src="https://github.com/bernardphh/500px-APIless/blob/master/Snapshots/Folders Structure.png" width ="25%">
 </p>
<br/>
If Python and Selenium are installed properly, you should be able to double-click the file 500px-APIless.py in Window Explorer to run it.

You can start the program in one of three following ways:<br/>

1.	Directly from the file 500px_APIless.py (double-click the script and follow the main menu)<br/>

2.	On the comand-line window (cmd.exe,  the Terminal Window). At the prompt, enter a single task.<br/>
   For example, to get the photos list: <br/> 
        (full path/)500px-APIless.py    --choice 2   --user_name   JohnDoe <br/>

3.	From a window shortcut to the script file, with all the needed arguments provided in the shortcut properties settings
Make many shortcuts as you like, each one for a specific task<br/>
<br/>
<br/>
Refer to the document [500px-APIless.docx] (https://github.com/bernardphh/500px-APIless/blob/master/500px-APIless.docx) for algorithm of each option, sample outputs and a complete command-line syntaxes.

<br/>

## SOME SAMPLE OUTPUTS: ##
<p align="center">
  <kbd><img src="https://github.com/bernardphh/500px-APIless/blob/master/Snapshots/CategorizedUsers.png" width ="70%">
  </kbd></p>
<br/><br/>

<p align="center"><kbd>
 <img src="https://github.com/bernardphh/500px-APIless/blob/master/Snapshots/15.4.All_users_with_following_statuses.png" width ="80%">
</kbd></p>
<br/><br/><br/>


<p align="center"><kbd>
 <img src="https://github.com/bernardphh/500px-APIless/blob/master/Snapshots/2.photos.png" width ="100%">
</kbd></p>
<br/>
<p align="center"><kbd>
 <img src="https://github.com/bernardphh/500px-APIless/blob/master/Snapshots/unlisted-limitedaccess.png" width ="100%">
</kbd></p>
<br/><br/><br/>


<p align="center"><kbd>
   <img src="https://github.com/bernardphh/500px-APIless/blob/master/Snapshots/16.1.All_recorded_notifications_from_local_db.png" width ="80%">
</kbd></p>
<br/><br/>

<p align="center"><kbd>
   <img src="https://github.com/bernardphh/500px-APIless/blob/master/Snapshots/16.2.UniqueUsersInAllNotifications.PNG" width="90%">
</kbd></p>
<br/><br/>

### Check if a user is following you: ###
<p align="center">
   <img src="https://github.com/bernardphh/500px-APIless/blob/master/Snapshots/6.CheckFollowingStatus.png" width="80%">
</p>
<br/><br/>

### Like n photos of each users in the last m notifications: ###
<p align="center">
   <img src="https://github.com/bernardphh/500px-APIless/blob/master/Snapshots/12.png" width="90%">
</p>
<br/><br/>

### Like n photos from a gallery: ###
<p align="center">
 <img src="https://github.com/bernardphh/500px-APIless/blob/master/Snapshots/9.details.PNG" width="90%">
</p><br/><br/>

### Playing a slideshow: ###
<p align="center">
    <img src="https://github.com/bernardphh/500px-APIless/blob/master/Snapshots/13.slideshow.png" width="90%">
</p>
<br/><br/><br/>

## LIMITATIONS, ISSUES, TO DO LIST: ##
<br/>

- Not all exceptions are handled, especially with Selenium’s find_element… methods
- For the requests involved more than 1000 items (list of notifications, photos, users…), processing time takes too long to my liking. 
- TODO: 
   - [x] Handling more exceptions
   - [x] Using WebDriverWait whenever possible, instead of time.sleep()
   - [x] Putting images thumbnails and user avatars in the result files
   - [ ] Adding ChromeCast support to slideshow
   - [x] Supporting command-line arguments
   - [ ] Playing slideshow in random order
   - [ ] Making a GUI 
   - [x] Automatic data analysis: photos, users and notifications
   - [x] Sorting a column in the output HTML file is too long to be practical, especially if the table is big (200+ rows). 
         Using jquery's DataTables for pagination, sort and search options.
         
   - [ ] Using multiprocessing (on processing already downloaded data, not on requests to servers)      

Prior to this project, I have zero knowledge about python and web scraping. No doubt there are rooms for improvements. 
I left abundant comments in the code to make the intention clear, just in case someone wants to chip in.

Feedback, bug report, contributions are more than welcomed.

<br/>

## DISCLAIMER: ## 

As in any web scraping, a change in page structure may break one or more options. 
Hopefully we can adapt when it happens, time and weather permitted.
Euh..., I meant time and mood permitted. (as I go older in age, my mood tends to change as quickly as weather. It can swing freely, unpredictably, to all direction :)  

As stated earlier, this project is created for fun and for gaining personal experience with python and web scraping. This were carried out in the most candid way. Some people may very well find this is not worth the effort, considering the fact that the pages keep changing and the site keeps evolving. 
But I will keep going as long as it stays fun. 

**The owner assumes no responsibility**.

Even though some limits have been set, and some processes have been intentionally slowed down to make it look more human, 
abusing or over-usage may result in your IP being temporary suspended, or your 500px account being banned. 

**Use this at your own risk**.

No web servers like being scraped. They are trying their best to prevent it. You need to take neccessary steps to avoid being detected and blacklisted. Rotating IP and user agents, among others, are some options that you may consider.  
For obvious reason, such measures are not included in the code.

**Stay clean, be reasonable and respectful, don't get caught and then Happy scraping !** )* 

<br/>
<br/>

## DEMO OF DATA COLLECTION RESULTS: ##

<br/>

<p align="center"><kbd>
 <img src="https://github.com/bernardphh/500px-APIless/blob/master/main-html-page_demo.gif" width ="100%">
</kbd></p>
<br/><br/><br/>
