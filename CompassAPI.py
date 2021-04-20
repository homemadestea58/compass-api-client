import requests, json, sys, re, html, urllib, time, os, subprocess, pickle, random, base64

class CompassAPI:
    # Don't use leading slash
    prefix = "https://compass-vic.compass.education"
    oktaPrefix = "https://example.okta.com"
    debug = True

    session = None;
    user = {}
    # Note - script isn't compatible with 2fa at the moment

    def __init__(self, debug = True):
        # Don't use leading slash for prefix
        # self.prefix = prefix
        # self.oktaPrefix = oktaPrefix
        self.debug = debug
        self.session = requests.Session()

        print(" Compass API Library")
        print("   Version 1.3.02  \n")

    def authenticate(self):
        if self.oktaPrefix != "disabled":
            return self.authenticateWithOkta()
        else:
            # TODO local auth
            return False

    def loadConfigFromFile(self, filename = "config.json"):
        try:
            with open(filename, "rb") as f:
                configData = json.loads(f.read())
                self.prefix = configData["schoolPrefix"]
                self.username = configData["username"]
                if "passwordBase64" in configData:
                    self.password = base64.b64decode(configData["passwordBase64"]).decode("utf-8", "ignore")
                else:
                    self.password = configData["password"]
                if configData["useOkta"]:
                    self.oktaPrefix = configData["oktaPrefix"]
                else:
                    self.oktaPrefix = "disabled"
        except Exception as e:
            print("Error loading configuration:")
            print(e)
            exit()

    def authenticateWithOkta(self):
        startTime = time.time()

        if not os.path.exists("saves"):
            print("Creating saves directory...")
            os.makedirs("saves")

        def printText(arg):
            if self.debug:
                print("  " + arg)

        jsonHeaders = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        try:
            with open("saves/session.pickle.save", "rb") as f:
                printText("Loading saved session file...")
                self.session.cookies.update(pickle.load(f))
                printText("Checking if session is valid...")
                if self.getInfoFromSession():
                    self.dumpSession()
                    return True
                else:
                    printText("Saved session is invalid or missing, re-authenticating with Compass:")
        except Exception:
            printText("Saved session file does not exist, or is corrupt. Re-authenticating with Compass:")

        def getFormValue(field, form):
            val = re.search('name="{field}".*?value="(.*?)"'.format(field = field), form)
            if val:
                return val.group(1)
            val = re.search('value="(.*?)".*?name="{field}"'.format(field = field), form)
            if val:
                return val.group(1)
            else:
                return None

        def getFormTarget(form):
            val = re.search('<form.*?action="(.*?)"', form)
            if val:
                return val.group(1)
            else:
                return None

        authnData = {
            'username': self.username,
            'password': self.password
        }

        authnData = json.dumps(authnData)

        printText("")
        printText("Establishing Okta session...")
        authnRequest = self.session.post(self.oktaPrefix + "/api/v1/authn", data = authnData, headers = jsonHeaders)
        printText("Parsing JSON response...")
        authnResponse = authnRequest.json()

        if "sessionToken" not in authnResponse:
            printText("Failed to authenticate through Okta, is your username/password or prefix correct?")
            printText("  Error ({code}): {summary}".format(code = authnResponse["errorCode"], summary = authnResponse["errorSummary"]))
            return False

        printText("Saving session token...")
        sessionToken = authnResponse["sessionToken"]

        printText("")
        printText("Getting SAML data from Compass...")
        compassSamlRequest = self.session.post(self.prefix + "/login.aspx?mobileSamlLogin=true")
        compassSamlResponse = compassSamlRequest.text

        printText("Parsing SAML data from Compass...")
        oktaFormOneData = {}
        oktaFormOneUrl = getFormTarget(compassSamlResponse)
        oktaFormOneData["SAMLRequest"] = getFormValue("SAMLRequest", compassSamlResponse)
        oktaFormOneData["RelayState"] = getFormValue("RelayState", compassSamlResponse)

        printText("")
        printText("Sending SAML data from Compass to Okta")
        oktaOneSamlRequest = self.session.post(oktaFormOneUrl, data = oktaFormOneData)
        oktaOneSamlResponse = oktaOneSamlRequest.text

        printText("Parsing Okta SAML request...")

        oktaFormTwoData = {}
        oktaFormTwoUrl = html.unescape(getFormTarget(oktaOneSamlResponse))
        oktaFormTwoData["SAMLRequest"] = html.unescape(getFormValue("SAMLRequest", oktaOneSamlResponse))
        oktaFormTwoData["RelayState"] = html.unescape(getFormValue("RelayState", oktaOneSamlResponse))

        printText("Preparing authentication data...")
        redirectUri = oktaFormTwoUrl + "?" + urllib.parse.urlencode(oktaFormTwoData)
        sessionRedirectUrl = self.oktaPrefix + "/login/sessionCookieRedirect?" + urllib.parse.urlencode({
                "checkAccountSetupComplete": "true",
                "token": sessionToken,
                "redirectUrl": redirectUri
        })

        printText("Authenticating with session token...")
        oktaAuthenticatedRequest = self.session.get(sessionRedirectUrl)
        oktaAuthenticatedResponse = oktaAuthenticatedRequest.text

        printText("")
        printText("Parsing Okta SAML response...")
        oktaFormThreeData = {}
        oktaFormThreeUrl = html.unescape(getFormTarget(oktaAuthenticatedResponse))
        oktaFormThreeData["SAMLResponse"] = html.unescape(getFormValue("SAMLResponse", oktaAuthenticatedResponse))
        oktaFormThreeData["RelayState"] = html.unescape(getFormValue("RelayState", oktaAuthenticatedResponse))

        printText("Sending SAML response to final Okta server...")
        oktaThreeSamlRequest = self.session.post(oktaFormThreeUrl, data = oktaFormThreeData)
        oktaThreeSamlResponse = oktaThreeSamlRequest.text

        printText("")
        printText("Parsing Okta SAML response...")
        compassPostBackData = {}
        compassPostBackUrl = html.unescape(getFormTarget(oktaThreeSamlResponse))
        compassPostBackData["SAMLResponse"] = html.unescape(getFormValue("SAMLResponse", oktaThreeSamlResponse))
        compassPostBackData["RelayState"] = html.unescape(getFormValue("RelayState", oktaThreeSamlResponse))

        printText("Sending SAML response back to Compass...")
        compassPostBackRequest = self.session.post(compassPostBackUrl, data = compassPostBackData, timeout=5)
        compassHomePageHTML = compassPostBackRequest.text

        printText("Extending user session...")
        self.post("/Services/mobile.svc/UpgradeSamlSession")

        printText("")

        self.dumpSession()
        self.getInfoFromSession()

        printText("Success - Authenticated with Compass in {0}s".format(round(time.time() - startTime, 2)))
        print("\n")

        return True

    def post(self, url, data = {}, cacheName = None, debug = True, timeout = 5):
        def makeRequest(url, data):
            return self.session.post(self.prefix + url, data = json.dumps(data), headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (X12; Linux x87_65; rv:89.0beta) Gecko/20100101 Firefox/89.0 Compass-Python-API",
                "X-Requested-With": "Compass-Python-API"
            }, timeout=timeout)
        #
        if cacheName is not None:
            if not os.path.exists("saves"):
                if debug: print("Creating saves directory...")
                os.makedirs("saves")
            try:
                with open("saves/{0}.save".format(cacheName)) as fileHandler:
                    if debug: print("Loading response (cached)")
                    return json.loads(fileHandler.read())
            except:
                if debug: print("Requesting data from Compass (not-cached)")
                request = makeRequest(url, data)
                open("saves/{0}.save".format(cacheName), 'w').write(request.text)
                return request.json()
        if debug: print("Requesting data from Compass (no-cache)")
        request = makeRequest(url, data)
        return request.json()

    def dumpSession(self):
        if not os.path.exists("saves"):
            print("Creating saves directory...")
            os.makedirs("saves")
        print("  Saving session to file...\n")
        with open('saves/session.pickle.save', 'wb') as f:
            pickle.dump(self.session.cookies, f)

    def getInfoFromSession(self, printInfo = True):
        # They both return very similar information - personal details api includes govtHealthcareNumber, immunisationRecordSighted, and medical
        # There is a switch here in case they shut one of the api's of - other one should still work
        useOption2 = True
        if not useOption2:
            if printInfo: print("  Requesting extended user...")
            endpoint = "/Services/Mobile.svc/GetExtendedUser"
        else:
            if printInfo: print("  Requesting extended user (o2)...")
            endpoint = "/Services/Mobile/UserAuthentication.svc/GetPersonalDetailsWithToken"
        infoRequest = self.session.post(self.prefix + endpoint, headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (X12; Linux x87_65; rv:89.0beta) Gecko/20100101 Firefox/89.0 Compass-Python-API",
            "X-Requested-With": "Compass-Python-API"
        }, timeout=2)
        if infoRequest.status_code is not 200:
            return False
        infoResponse = infoRequest.json()
        self.user = infoResponse["d"]["data"]
        if printInfo: print("  Signed in as: {0} ({1})".format(self.user["reportName"], self.user["userId"]))
        return True



if __name__ == '__main__':
    print("Please run this script through another python script in this way:")
    print('''
import authHelper
authResult = authHelper.main(compassPrefix, oktaPrefix, username, password);

s = authResult["session"] # Use like a requests object: e.g s.get(url), s.post(url, data = data)
userId = authResult["userId"] # The userId of the user currently signed into Compass
    ''')
