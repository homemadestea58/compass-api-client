import base64

from CompassAPI import CompassAPI

# pip3 install python-Levenshtein
# pip3 install termtables
from Levenshtein import distance
import termtables as tt

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

searchName = input("Enter your search query (full names will be searched) -> ")
searchName = searchName.lower()

users = Compass.post("/Services/User.svc/GetNamesById", {
    "limit": 1000000, # this can safely be set very high - and I doubt there will ever be a million users in compass!
    "page": 1,
    "start": 1,
    "userIds": list(range(1, 10000))
}, timeout = 20)["d"]

print("Scanning users for matches...")

results = []

for user in users:
    user["dist"] = distance(searchName, user["n"])
    if (searchName in user["n"].lower()):
        user["dist"] = user["dist"] - 10
        if (user["n"].lower().startswith(searchName)):
            user["dist"] = user["dist"] - 5
    results.append(user)

results = sorted(results, key=lambda k: k["dist"])[0:10]
userResults = []

for result in results:
    userId = result["id"]
    userName = result["n"]
    userResults.append([userId, userName])

print("10 most relevant results")
tt.print(userResults, header = ["User ID", "Full Name"], style = tt.styles.rounded_thick)
