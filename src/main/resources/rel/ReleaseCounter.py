import sys

import com.xhaus.jyson.JysonCodec as json

def get_counter_store_ci(counterStoreTitle):
    conn_fac = HttpRequest({'url': 'http://localhost:5516'}, str(release.scriptUsername), str(release.scriptUserPassword))

    response = conn_fac.get(str('/configurations'), contentType = 'application/json')

    data = json.loads(response.getResponse())


    counter_store_ci = None

    for i in range(0, len(data)):
        if data[i]['type'] == 'rel.ReleaseCounterStore' and counterStoreTitle == data[i]['properties']['title']:
                print data
                counter_store_ci = data[i]
                break

    if not counter_store_ci:
        print "ERROR: Unable to find counter store '%s'" % (counterStoreTitle)
        sys.exit(1)


    return data[0]

def save_counter_store(counterStoreTitle, storageDict):
    conn_fac = HttpRequest({'url': 'http://localhost:5516'}, release.scriptUsername, release.scriptUserPassword)
    counter_store_ci = get_counter_store_ci(counterStoreTitle)

    counter_store_ci['properties']['counterStorage'] = json.dumps(storageDict)

    response = conn_fac.put('/configurations/%s' % (counter_store_ci['id']), json.dumps(counter_store_ci), contentType = 'application/json')
    print response
    if not response.isSuccessful:
        print "ERROR: Unable to update counter store '%s':" % (counterStoreTitle)
        response.errorDump()
        sys.exit(1)

def get_counter_store_storage(counterStoreTitle):
    cs = get_counter_store_ci(counterStoreTitle)
    print type(cs)
    if type(cs) != dict:
        print "ERROR: unexpected response from counter Store: %s" % counterStoreTitle
        sys.exit(1)

    return json.loads(cs['properties']['counterStorage'])

def create_or_update_counter(counterStoreTitle, key, value):
    store = get_counter_store_storage(counterStoreTitle)
    store[key] = value
    print store
    save_counter_store(counterStoreTitle, store)

def get_counter_value(counterStoreTitle, key):
    cs = get_counter_store_storage(counterStoreTitle)
    print cs[key]

    return cs[key]

print taskAction
if taskAction == 'set':
    print "setting release counter"
    create_or_update_counter(counterStore, counterName, counterValue)
elif taskAction == 'get':
    print "getting release counter"
    outputVariable = get_counter_value(counterStore, counterName)
elif taskAction == 'increment':
    print "incrementing release counter"
    outputVariable = get_counter_value(counterStore, counterName)
    outputVariable = outputVariable + 1
    create_or_update_counter(counterStore, counterName, outputVariable)
else:
    print "nothing to do "