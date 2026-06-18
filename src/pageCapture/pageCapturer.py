from fileinput import close
import io
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.firefox.options import Options  
from time import sleep
from pathlib import Path
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

from win32gui import GetWindowText, GetForegroundWindow
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from selenium.webdriver.support.select import Select
from daveConnection import daveConnection, getTrueDomain

class pageCapturer:
    
    __MAX_PAGE_LOAD_TIMEOUT = 30

    _tmpSiteName = "tempSite.htm"
    __fullTmpFileName = None
    __theWindowHandle = None
    __winhand= None
    __connection = None
    _driver = None
    __headless = False

    def __init__(self, useChrome=False,headless=False,consoleWindow=True):
      self.__connection = daveConnection()

      downloads_path = str(Path.home() / "Downloads")
      self.__fullTmpFileName = downloads_path+"\\"+self._tmpSiteName
      if useChrome:
        caps = DesiredCapabilities.CHROME
        caps['goog:loggingPrefs'] = {'performance': 'ALL'}
        #self.__driver = webdriver.Chrome(desired_capabilities=caps)
      
        options = webdriver.ChromeOptions()
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        options.add_argument('ignore-certificate-errors')
        options.add_argument('--allow-running-insecure-content')
        options.add_argument("--auto-open-devtools-for-tabs")
        #options.add_argument("--headless=new")
       # options.add_argument("--auto-open-devtools-for-tabs")
        self._driver = webdriver.Chrome(chrome_options=options, desired_capabilities=caps)
        self._driver.set_page_load_timeout(self.__MAX_PAGE_LOAD_TIMEOUT)
      else:
        FF_options = Options()
        if consoleWindow is True:
          FF_options.add_argument("-devtools")
        if headless:
           self.__headless=True
           FF_options.add_argument( "--headless" )
        self._driver = webdriver.Firefox(options=FF_options,service=FirefoxService(GeckoDriverManager().install()))
        self._driver.implicitly_wait(10)
        self._driver.set_script_timeout(10)

      self.__theWindowHandle = self._driver.window_handles[0]
      sleep(3)
      
      self._driver.set_window_size(1292, 1205)
      #keyboard.send(['ctrl', 'shift','i'])
      #sleep(1.5)
      # sleep(1)
      # print ("sendddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd")
      # sleep(7)
      # ActionChains(self.__driver).key_down(Keys.CONTROL).send_keys('c').key_up(Keys.CONTROL).perform()
      # sleep(7)
      # ActionChains(self.__driver).key_down(Keys.CONTROL).send_keys("s").key_up(Keys.CONTROL).perform()
      # actions.send_keys(Keys.CONTROL,'s')
      # sleep(1)
      # actions.send_keys(Keys.CONTROL,'s').perform()
      # sleep(1)
      # actions.send_keys(Keys.CONTROL+'s').perform()
      # sleep(1)
      # actions.send_keys(Keys.CONTROL+'S').perform()
      # sleep(1)
      # actions.send_keys(Keys.CONTROL,'S').perform()
      # sleep(2)

    def __del__(self):
      if self._driver is not None:
        try:
          self._driver.close()
        except Exception:
           return None

    def close(self):
      if self._driver is not None:
        try:
          self._driver.quit()
        except Exception:
           return None

    def _removeOldTextFile(self):
        if os.path.isfile(self.__fullTmpFileName):
          os.remove(self.__fullTmpFileName)

    def _waitForFileWrite(self,aFileName):
        maxSleepCount = 60  #max wait of 60 seconds
        prtCount = 0
        while not os.path.isfile(self.__fullTmpFileName) and maxSleepCount > 0:
          sleep(1.0)
          maxSleepCount = maxSleepCount -1
          if prtCount ==8:
              print ("           waiting for file.......................")
              prtCount = 0
          else:
              prtCount =prtCount + 1
        
        
        if maxSleepCount > 0:
          return "ok"
        print("file not readyyyyyyyyyyyyyyyyyyyyyyyyyy")
      
        #if self.__driver is not None:
         # try:
           # print ("switch to alert")
           # self.__driver.switch_to().alert().accept()
           # print ("accept")
            #alert.accept() # or alert.dismiss(); to cancel the alert
           # print ("after accept")
         # except webdriver.NoAlertPresentException as e: 
         #   None
        return None

    def __waitForSeleniumBrowserToBeInFocus(self):
      winInfo = GetWindowText(GetForegroundWindow())
      if winInfo.find("Mozilla Firefox") == -1:
          print ("\n******************************************************************************************")
          print ("                     main window must be Selenium browser                              ")
      cnt=0
      outOfFocus = False
      while winInfo.find("Mozilla Firefox") == -1:
          if cnt == 5:
             cnt=0
             print ("                     Selenium browser window must be in focus                      ")
             outOfFocus = True
          else:
              print ("waiting .........")
          cnt=cnt+1
          sleep (5)
          winInfo = GetWindowText(GetForegroundWindow())
      if outOfFocus:
        print ("Selenium window now in focus")

    def __getAndSaveSiteToFile(self,aSiteURL):
        if self.getSite(aSiteURL) is None:
           return None
        return self.__saveSiteToFile()
    
    def __saveSiteToFile(self):
        self._removeOldTextFile()
        sleep(5)
        html = self._driver.page_source
        with io.open(self.__fullTmpFileName, "w", encoding="utf-8") as f:
            f.write(html)
            f.close()
        # if self.__headless:
        #   actions = ActionChains(self._driver)
        #   print ("start sendingggggggggggggggggggggggggggggggggggggggggggg")
        #   actions.key_down(Keys.CONTROL).send_keys('s').key_up(Keys.CONTROL).perform()
          # actions.send_keys(Keys.CONTROL,'s')
          # sleep(1)
          # actions.send_keys(Keys.CONTROL,'s').perform()
          # sleep(1)
          # actions.send_keys(Keys.CONTROL+'s').perform()
          # sleep(1)
          # actions.send_keys(Keys.CONTROL+'S').perform()
          # sleep(1)
          # actions.send_keys(Keys.CONTROL,'S').perform()
        #   sleep(2)
        #   self.takeScreenshot("AAone.png")
        #   actions.send_keys(self._tmpSiteName+"\r\n").perform()
        #   sleep(1)
        #   self.takeScreenshot("AAtwo.png")
        # else:
        #   sleep(0.3)
        #   self.__waitForSeleniumBrowserToBeInFocus()
        #   keyboard.send(['ctrl', 's'])
        #   sleep(1)
        #   keyboard.write(self._tmpSiteName+"\r\n")
        retStatus = self._waitForFileWrite(self._tmpSiteName)
        self._driver.close()
        return retStatus

    def _getTextSiteFromFile(self):
      filehnd = open(self.__fullTmpFileName, "r", encoding="utf8")
      textFromFile = None
      try:
        textFromFile= filehnd.read()
      except Exception as e:
        filehnd = open(self.__fullTmpFileName, "r") 
        try:
          textFromFile= filehnd.read()
        except Exception as e:
           print (e)
      filehnd.close()
      return textFromFile
      
    def addTextToIDInputField(self,idName,textToAdd):
       inputField=self._driver.find_element(By.ID,idName)
       #inputField.clear()  
       inputField.send_keys(textToAdd)  

    def daveInit(self):
        self._driver.implicitly_wait(3)
        self._driver.set_script_timeout(3)

    def addTextToCLASSInputField(self,className,textToAdd):
       inputField=self._driver.find_element(By.CLASS_NAME,className)
       inputField.clear()  
       inputField.send_keys(textToAdd)  
    
    def selectDropDownByDoubleXpath(self,sectionXpath,xpath): 
      select_element = self._driver.find_element(By.XPATH,sectionXpath)
      select_element.click()
      try:
        elementToSelect = select_element.find_element(By.XPATH,xpath)
        elementToSelect.click() 
        ActionChains(self._driver) \
        .double_click(elementToSelect) \
        .perform()
        a=1
      except Exception as e:
         print(e)
    
    # partially works. It brings up the file chooser. Selenium can't interact with this native dialog
    def fileUpload(self,fullPathFileName,IDelement,xpathOfClickElement): 
      select_element = self._driver.find_element(By.ID,IDelement)
      try:
        elementToSelect = select_element.find_element(By.XPATH,xpathOfClickElement)
        elementToSelect.click() 
        ActionChains(self._driver) \
        .double_click(elementToSelect) \
        .perform()
        a=1
      except Exception as e:
         print(e)


    def davetest(self): 
      select_element = self._driver.find_element(By.ID,'fo3li31')
      try:
        elementToSelect = select_element.find_element(By.XPATH,'//*[@id="fo3li31"]/div/div/div')
        elementToSelect.click() 
        ActionChains(self._driver) \
        .double_click(elementToSelect) \
        .perform()
        a=1
      except Exception as e:
         print(e)


    def selectDropDownByXpath(self,sectionID,xpath):
      select_element = self._driver.find_element(By.ID,sectionID)
      mainDiv = select_element.find_element(By.CLASS_NAME,'wufoo-dropdown-control')
      mainDiv.click()
      try:
        self._driver.execute_script("window.scrollTo(0, 300)")
        elementToSelect = select_element.find_element(By.XPATH,xpath)
        elementToSelect.click()
        ActionChains(self._driver) \
        .double_click(elementToSelect) \
        .perform()
      except Exception as e:
         print(e)
       

    def getFinalUrl(self):
       return  self._driver.current_url
       
    def getUNSAFE(self,aUrl):
      try:
        self._driver.get(aUrl)
      except TimeoutError:
         print ("max page timeouttttttttttttttttttttttttttttttttt")
         return None
     
    def getSite(self,aUrl):
      # Confirm page exists with requests library then get deep page with webdriver
      status_code = self.__connection.connect(aUrl)
      if not (status_code >= 200 and status_code < 400) and status_code != 403 and status_code != 406:
        print ("  *** Response status code = ",status_code)
        return None
      if status_code ==429:
          print ("$$$$$$$$$$$$$$$$$$$$$$$$  TOO MANY REQUESTS  url=",aUrl, "   $$$$$$$$$$$$$$$$$$$$")

      try:
        print ("## get URL from selenium browser ##")
        self._driver.get(aUrl)
        print ("## AFTER get URL from selenium browser ##")
      except TimeoutError:
         print ("max page timeouttttttttttttttttttttttttttttttttt")
         return None
      except Exception:
         return None
      #driver waits for the page to load but a delay is needed for any javascript to process
      # wait for several seconds if page isn't loaded
      return "ok"
    
    def __findYCoorOfPlacesOrBusinessOnVisibleScreen(self):
      yCoor=-1
      try:
          #placesLocation=self._driver.find_elements(By.CSS_SELECTOR, "[aria-label='Location Results for Places']")
          placesLocation=self._driver.find_elements(By.CSS_SELECTOR, "[aria-label='Location Results for Places']")
          yCoor=placesLocation[0].location['y']
      except Exception:
         pass
      
      if yCoor == -1:
        try:
          placesAltLocation=self._driver.find_element_by_xpath("//*[text()='Places']")
          yCoor=placesAltLocation.location['y']
        except Exception as e:
          pass

      if yCoor == -1:
        try:
          businesssLocation=self._driver.find_elements(By.CSS_SELECTOR, "[aria-label='Location Results for Businesses']")
          yCoor=businesssLocation[0].location['y']
        except Exception:
          pass

      return yCoor
      

    def __scrollToPlacesOrBusinessLocation(self):
      for retries in range (3):
         yCoor=self.__findYCoorOfPlacesOrBusinessOnVisibleScreen()
         if yCoor > -1:
           self.scrollDown(yCoor-200)
           return
         sleep(2)
         self.scrollDown(800)

    def getGoogleQueryResults(self,termString):

      if self.getSite("https://www.google.com") is None:
         return None
      search_box = self._driver.find_element_by_name('q')
      search_box.send_keys(termString)
      search_box.send_keys(Keys.RETURN)
      self.__scrollToPlacesOrBusinessLocation()

      self.__saveSiteToFile()
      return self._getTextSiteFromFile()

    def getGoogleMapLink(self,geoArea):
      if self.getSite("https://www.google.com/maps/") is None:
         return None
      search_box = self._driver.find_element(By.NAME,'q')
      search_box.send_keys(geoArea)
      search_box.send_keys(Keys.RETURN)

      WAIT_FOR_URL_TO_SETTLE_IN_BROWSER = 10  # otherwise url will return as google.com/maps only
      sleep(WAIT_FOR_URL_TO_SETTLE_IN_BROWSER)
      
      return self._driver.current_url
    
    def scrollTop(self):
       cmd="window.scrollTo(0,0)"
       self._driver.execute_script(cmd)
       
    def scrollDown(self,yPosition):
       cmd="window.scrollTo(0, "+str(yPosition)+")"
       self._driver.execute_script(cmd)

    
    def takeScreenshot(self,filepath):
       self._driver.save_screenshot(filepath)

    def login(self,aUrl,aUserNameField,aUserName,aPassField,aPassword):
      if self.getSite("https://www.facebook.com/") is None:
         return None
   
      username = self._driver.find_element(By.ID, aUserNameField)
      password = self._driver.find_element(By.ID, aPassField)

      username.send_keys(aUserName)
      password.send_keys(aPassword)

      pth="//*[contains(@id,'u_0_5')]"
      submit = self._driver.find_element(By.XPATH, pth)
      submit.click() 
      sleep(5)  
      return "ok"
      
    def getSiteAsText(self,aSiteUrl):
      if self.__getAndSaveSiteToFile(aSiteUrl) is None:
         print("url failed to save locally URL="+aSiteUrl)
         return None
      return self._getTextSiteFromFile()
    
    def getActualURL(self):
       return self._driver.current_url


# pg = davepage(False,True)
# mapLink = pg.getGoogleMapLink("chicago, il")
# print (mapLink)
#aaaa=pg.getSiteAsText("https://www.greenwichtime.com/business/article/Yoga-therapy-help-children-thrive-8384796.php")

