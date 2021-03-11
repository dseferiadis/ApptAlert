# Import Modules
import requests
import config
import time
from datetime import datetime
from pygame import mixer


def get_zipcodes(zipcode, radius):
    print("Searching for zip codes within " + str(radius) + " mile(s) of " + str(zipcode))
    zipcodes = requests.get(config.zipcode_url + "/" + config.zipcode_api_key + "/radius.json/" + str(zipcode) + "/" +
                            str(radius) + "/mile").json()
    if config.verbose:
        print("Found " + str(len(zipcodes['zip_codes'])) + " zip codes!")
    return zipcodes['zip_codes']


def get_stores(zipcode, radius):
    stores = config.preferred_stores
    zipcodes = get_zipcodes(zipcode, radius)
    print("Getting RiteAid stores in target zip code(s)")
    for zipcode in zipcodes:
        localstores = store_search(zipcode['zip_code'], config.riteaid_store_radius, 0)
        localstoreqty = 0
        if localstores is not None:
            localstoreqty = len(localstores)
        if localstoreqty > 0:
            for localstore in localstores:
                if localstore['storeNumber'] not in stores.keys():
                    stores[localstore['storeNumber']] = {'zipcode': localstore['zipcode'],
                                                         'address': localstore['address'],
                                                         'city': localstore['city'],
                                                         'state': localstore['state'],
                                                         'rank': 0,
                                                         'last_attempt_with_availability': 0}
    return stores


def store_search(zipcode, radius, attempt):
    if attempt > config.web_retry_qty:
        return None
    else:
        attempt = attempt + 1
        try:
            if config.verbose:
                print("Searching within " + str(radius) + " mile(s) of " + str(zipcode))
            json_payload = {'address': zipcode,
                            'attrFilter': 'PREF-112',
                            'fetchMechanismVersion': '2',
                            'radius': radius}
            stores = requests.get(config.riteaid_store_url, json_payload).json()
            if stores['Data'] is None or stores['Data']['stores'] is None:
                return None
            if config.verbose:
                print(" Found " + str(len(stores['Data']['stores'])) + " store(s)!")
            return stores['Data']['stores']
        except:
            store_search(zipcode, radius, attempt)


def get_appt(store, attempt):
    if attempt > config.web_retry_qty:
        return None
    else:
        attempt = attempt + 1
        try:
            if config.verbose:
                print("Checking Store: " + str(store))
            json_payload = {'storeNumber': store}
            appts = requests.get(config.riteaid_checkslot_url, json_payload).json()
            if appts['Data'] is None or appts['Data']['slots'] is None:
                return None
            else:
                return appts['Data']['slots']
        except:
            get_appt(store, attempt)


def is_store_excluded(store):
    try:
        t = config.excluded_store[store]
        return True
    except IndexError:
        return False


def is_store_preferred(store):
    try:
        t = config.preferred_stores[store]
        return True
    except IndexError:
        return False


def get_store_status(store):
    slots = get_appt(store, 0)
    if slots is None:
        return False
    elif (slots['1'] is not False or slots['2'] is not False) and not is_store_excluded(store):
        return True
    else:
        return False


def get_store_availability(store, method, stores_api_json):
    if method == 'API':
        for api_store in stores_api_json['features']:
            if api_store['properties']['appointments_available']:
                if api_store['properties']['name'] == 'Rite Aid' and \
                        int(api_store['properties']['provider_location_id']) == store:
                    return True
        return False
    elif method == 'DIRECT':
        return get_store_status(store)
    else:
        return None


def check_stores(stores, attempt, method):
    # Method is either API or DIRECT to go to RiteAid
    attempt = attempt + 1

    if method == 'API':
        stores_api_json = requests.get(config.vaccinespotter_url).json()

    for store in stores:
        # Check if store is preferred
        preferredtext = ''
        alertfile = 'alert.mp3'
        if is_store_preferred(store):
            alertfile = 'preferred.mp3'
            preferredtext = '-->'

        # Check for Availability
        if get_store_availability(store, method, stores_api_json):
            # Play Alert!
            # https://notificationsounds.com/sound-effects
            mixer.init()
            mixer.music.load(alertfile)
            mixer.music.play()
            stores[store]['rank'] = stores[store]['rank'] + 1
            stores[store]['last_attempt_with_availability'] = attempt
            successpct = int((float(stores[store]['rank']) / attempt) * 100)
            print(preferredtext + stores[store]['address'] + " " + stores[store]['city'] + ", " +
                  stores[store]['state'] + " " + str(stores[store]['zipcode']) + " Store:" + str(store) + " Rank:" +
                  str(stores[store]['rank']) + " (" + str(successpct) + "%)")

        if attempt > config.retries:
            # Print Summary of Stores by Availability
            stores_by_availability(stores)
            return
        else:
            now = datetime.now()
            current_time = now.strftime("%H:%M:%S")
            print("   Completed attempt " + str(attempt) + " of " + str(config.retries) + " at " + current_time +
                  " - Sleeping " + str(config.sleep_sec) + " second(s)")
            time.sleep(config.sleep_sec)
            check_stores(stores, attempt, method)


def stores_by_availability(stores):
    print("")
    print("Stores by Rank")

    # Get Max Availability
    maxavailability = 0
    for store in stores:
        if int(stores[store]['rank']) > maxavailability:
            maxavailability = int(stores[store]['rank'])
    storeswithavailability = 0
    i = maxavailability
    while i > 0:
        for store in stores:
            if int(stores[store]['rank']) == i:
                storeswithavailability = storeswithavailability + 1
                successpct = int((float(stores[store]['rank']) / config.retries) * 100)
                print(stores[store]['address'] + " " + stores[store]['city'] + ", " + stores[store]['state'] + " " +
                      str(stores[store]['zipcode']) + " Store:" + str(store) + " Rank:" + str(stores[store]['rank'])
                      + " (" + str(successpct) + "%)")
        i = i - 1
    if storeswithavailability == 0:
        print("No store(s) with availability!")


print("Starting ApptAlert")
storelist = get_stores(19454, 5)
print("   " + str(len(storelist)) + " stores to check!")

print("Checking stores " + str(config.retries) + " times with " + str(config.sleep_sec) + " second delay")
check_stores(storelist, 0, 'API')
