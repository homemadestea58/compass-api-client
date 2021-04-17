from CompassAPI import CompassAPI

Compass = CompassAPI(
    prefix = "https://compass-vic.compass.education",
    oktaPrefix = "https://example.okta.com",
    debug = True
)

authenticationStatus = Compass.authenticateWithOkta(
    username = "me",
    password = "me"
)

if not authenticationStatus:
    print("Authentication error!")
    exit(1)

print("Demo script to demonstrate CompassAPI.py")

targetUserId = int(input("Target UserId -> "))

basicUserInfo = Compass.post("/Services/User.svc/GetNamesById", {
    "limit": 1,
    "page": 1,
    "start": 0,
    "userIds": [targetUserId]
}, debug = True)

print(basicUserInfo)
