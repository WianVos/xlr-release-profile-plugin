# THIS CODE AND INFORMATION ARE PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESSED OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED WARRANTIES OF MERCHANTABILITY AND/OR FITNESS
# FOR A PARTICULAR PURPOSE. THIS CODE AND INFORMATION ARE NOT SUPPORTED BY XEBIALABS.
#
# from XLRProfile import XLRProfile as XLRProfile
#
import sys
import re
import collections
import time
import random
import pprint

import requests
from Base import Base
import com.xhaus.jyson.JysonCodec as json
from com.xhaus.jyson import JSONDecodeError
from requests.auth import HTTPBasicAuth
import com.xebialabs.xlrelease.api.XLReleaseServiceHolder as XLReleaseServiceHolder
import com.xebialabs.deployit.repository.SearchParameters as SearchParameters
import com.xebialabs.deployit.plugin.api.reflect.Type as Type
import com.xebialabs.xlrelease.builder.PhaseBuilder as PhaseBuilder
import com.xebialabs.xlrelease.domain.status.PhaseStatus as PhaseStatus


class CollectorError(Exception):
    """Exception raised for errors in the input.

    Attributes:
        expr -- input expression in which the error occurred
        msg  -- explanation of the error
    """

    def __init__(self, value, msg):
        self.value = value
        self.msg = msg

    def __str__(self):
        return "%s : %s" % (self.msg, self.value)


class Collector():
    """
    base class for all collectors
    takes care of validating that all collector needed parameters are passed in
    """

    attributes = []
    optional_attributes = []

    def __init__(self, **params):
        self.validate(**params)

    def validate(self, **params):
        for a in self.attributes:
            if params.has_key(a) is not True:
                raise CollectorError(a, "unable to satisfy all attributes")

    def resolve(self):
        return None


class JsonCollector(Collector):
    attributes = ["url", "path"]
    optional_attributes = []

    def __init__(self, **params):

        Collector.__init__(self, **params)

        self.requests_params = {}

        if params.has_key('username') and params.has_key('password'):
            self.requests_params['auth'] = HTTPBasicAuth(params['username'], params['password'])

        self.__collector_params = params

    def resolve(self):
        """
        resolve the collector
        :return: string
        """
        return self.get_path(self.load_json(self.__collector_params['url']), self.__collector_params['path'])

    def load_json(self, url):
        """
        loads json from a url and translates it into a dictionary
        :param url:
        :return:
        """

        # adding in retry to make all this stuff a little more robust
        # if all else fails .. we are going to retry 10 times ..
        retries = 10
        nr_tries = 0

        output = None

        while True:
            # increment trie counter
            nr_tries += 1
            Base.info("trying to fetch json from url %s , try nr: %i" % (url, nr_tries))


            # try to fetch a response
            response = requests.get(url, verify=False, **self.requests_params)

            # if the status code is above 299 (which usually means that we have a problem) retry
            if response.status_code > 299:

                # if the number of retries exceeds 10 fail hard .. cuz that is how we roll
                if nr_tries > retries:
                    Base.fatal('Unable to retrieve json from url after %i retries' % retries)
                    sys.exit(2)

                # warn the user
                Base.warning("unable to retrieve json from url: %s" % url)

                # it is good form to back off a failing remote system a bit .. every retry we are gonna wait 5 seconds longer . Coffee time !!!!
                sleeptime = 5 * int(nr_tries)

                Base.warning("timing out for: %i seconds" % sleeptime)

                # sleep dammit .. i need it ..
                time.sleep(sleeptime)
                output = None
            else:
                # if we do get a proper response code .. break out of the loop
                break

        try:
            Base.info("%s responded with:" % url)
            print response.text
            output = json.loads(str(response.text))

        except Exception:
            Base.warning("unable to decode information provided by %s" % url)
            time.sleep(5)
            output = None
        except JSONDecodeError:
            Base.warning("unable to decode output, not json formatted")
            time.sleep(5)
            output = None

        if output == None:
            Base.error("unable extract information from url: %s " % url)

        return output

    def get_path(self, json, path):
        """
        traverses the dictionary derived from the json to look if it can satisfy the requested path
        :param json:
        :param path:
        :return:
        """

        if (type(path) is str) or (type(path) is unicode):
            path = str(path).split('/')

        field = path.pop(0)

        try:
            if json.has_key(field):
                if type(json[field]) == dict:
                    return self.get_path(json[field], path)

                elif type(json[field]) == list:
                    if len(json[field]) < 2:
                        Base.info("found %s" % (json[field][0]))
                        return str(json[field][0])

                elif len(path) == 0:
                    Base.info("found %s using path %s" % (field, path))
                    return str(json[field])
            else:
                Base.warning("the requested path of %s could not be found in the json document. returning None instead")
                return None
        except Exception:
            Base.error("Error encountered during resolution")


class XLRProfile(collections.MutableMapping):
    """A dictionary that applies an arbitrary key-altering
       function before accessing the keys"""

    def __init__(self, *args, **kwargs):
        """
        TODO: need to come up with a way to resolve variables used inside the profile
                Best way to do this i think is to pull all available variables form the xlr context and match the
                dictonary's values against them
        :param args:
        :param kwargs:
        :return:
        """

        # pull in the xlrelease apis
        self.__releaseApi = XLReleaseServiceHolder.getReleaseApi()
        self.__repositoryService = XLReleaseServiceHolder.getRepositoryService()
        self.__taskApi = XLReleaseServiceHolder.getTaskApi()
        self.__phaseApi = XLReleaseServiceHolder.getPhaseApi()

        self.__variable_start_regex = re.compile('\$\{', re.IGNORECASE)
        # TODO: replace with {} once testing is done

        self.__variable_start_string = "$<"
        self.__variable_end_string = ">"

        self.store = dict()

        if kwargs.has_key('url'):
            kwargs = self.load_from_url(kwargs['url'])
        elif kwargs.has_key('repoId'):
            kwargs = self.load_profile_from_xlr_repo(kwargs['repoId'])
        elif kwargs.has_key('repoString'):
            kwargs = json.loads(str(kwargs['repoString']))

        self.update(dict(*args, **kwargs))  # use the free update to set keys

    def resolve_xlr_template_variables(self, release_id, var_dict=None):

        # if no var_dict specified get the profiles variables as default action
        if var_dict == None:
            var_dict = self.variables()

        for k, v in var_dict.items():
            if type(v) == dict:
                var_dict[k] = self.resolve_xlr_template_variables(release_id, v)
            if type(v) == str or type(v) == unicode:
                v = str(v)
                if '${' in v:
                    Base.info("found variable in %s" % v)

                    for x, y in self.get_release_variables(release_id).items():
                        if x in v:
                            print "REPLACE"
                            Base.info("replacing variable %s with value %s" % (x, y))
                            v = v.replace(x, y)
                            var_dict[k] = v

        return var_dict

    def get_release_variables(self, release_id):
        release = self.__releaseApi.getRelease(str(release_id))
        return release.getVariableValues()


    def __getitem__(self, key):
        if self.store.has_key(self.__keytransform__(key)):
            return self.store[self.__keytransform__(key)]
        else:
            return None

    def __setitem__(self, key, value):
        self.store[self.__keytransform__(key)] = value

    def __delitem__(self, key):
        if self.store.has_key(self.__keytransform__(key)):
            del self.store[self.__keytransform__(key)]

    def __iter__(self):
        return iter(self.store)

    def __len__(self):
        return len(self.store)

    def __keytransform__(self, key):
        return key

    def variables(self):
        return self.__getitem__('variables')

    def set_variable(self, key, value):
        self.store['variables'][key] = value

    def set_variables_from_dict(self, var_dict):
        self.store['variables'] = var_dict

    def toggles(self):
        return self.__getitem__('toggles')

    def template_plan(self):
        return self.__getitem__('template_plan')

    def set_template_plan_from_dict(self, template_plan_dict):
        self.store['template_plan'] = template_plan_dict

    def settings(self):
        return self.__getitem__('settings')

    def set_settings_from_dict(self, settings_dict):
        self.store['settings'] = settings_dict

    def load_from_url(self, url):
        """
        reaches out to a url and loads the profile
        :param url:
        :return: dict: profile
        """
        print type(url)
        if type(url) == list:


            # if we are fed a list of urls
            # resolve each one and merge them with the later url taking precedence
            outputDict = {}
            for u in url :
                Base.info("Attempting to fetch profile at: %s" % u)
                response = requests.get(u, verify=False)
                response.raise_for_status()
                print json.loads(str(response.text))
                outputDict = dict(self.merge_profiles(outputDict, json.loads(str(response.text))))
            pprint.pprint(outputDict)
            return outputDict

        else:
            response = requests.get(url, verify=False)
            response.raise_for_status()

            return json.loads(str(response.text))

    def merge_profiles(self, dict1, dict2):
        """
        Merge two profiles in the order they where loaded in. The latter overwrites the former
        :param dict1:
        :param dict2:
        :return:
        """
        for k in set(dict1.keys()).union(dict2.keys()):
            if k in dict1 and k in dict2:
                if isinstance(dict1[k], dict) and isinstance(dict2[k], dict):
                    yield (k, dict(self.merge_profiles(dict1[k], dict2[k])))
                elif isinstance(dict1[k], list) and isinstance(dict2[k], list):
                    yield(k, dict1[k] + [i for i in dict2[k] if i not in dict1[k]])

                else:
                    # If one of the values is not a dict, you can't continue merging it.
                    # Value from second dict overrides one in first and we move on.
                    yield (k, dict2[k])
                    # Alternatively, replace this with exception raiser to alert you of value conflicts
            elif k in dict1:
                yield (k, dict1[k])
            else:
                yield (k, dict2[k])


    def load_profile_from_xlr_repo(self, profileName):
        """
        load the profile from the xlr repository
        :param profileName: name of the profile as it was configured
        :return:
        """
        sp = SearchParameters()
        sp.setType(Type.valueOf('rel.ReleaseProfile'))

        for p in self.__repositoryService.listEntities(sp):
            if str(p.getTitle()) == profileName:
                return json.loads(p.getProperty('profileJson'))

    def resolve_variables(self):

        for key, val in self.variables():
            if type(val) == dict:
                solution = self.resolve_variable(val)
                if solution == None:
                    Base.fatal("value for %s could not be found using the specified collector" % key)
                    sys.exit(2)
                else:
                    Base.info("retrieved value: %s for %s" % (solution, key))
                self.set_variable(key, solution)

    def resolve_variable(self, **params):
        """
        try to resolve the variable with the information specified
        params can handle:
        :default_value string: the default value to set in case no value could be retrieved
        :collector dict: information used retrieve the value from an additional source
        :param params:
        :return: result for the resolve attempt
        """

        # set our return value to None
        ret_val = None
        collector_val = None

        # start by setting the default value if specified
        if params.has_key('default_value'):
            ret_val = params['default_value']

        # act on the collector parameter
        if params.has_key('collector'):
            # if there is no type specified just pass it to the json collector, which is our default choice
            # if not params['collector'].has_key('type'):
            #     collector_val = self.handle_json_collector(**params['collector'])
            # if params['collector'].has_key('type'):
            #     collector_val = self.handle_json_collector(**params['collector'])
            # else:
            #     print "collector type is not supported.... yet!!!"
            #     sys.exit(2)
            # if there is no type specified just pass it to the json collector, which is our default choice
            if not params['collector'].has_key('type'):
                col_params = params['collector']
                collector_val = JsonCollector(**col_params).resolve()
            if params['collector'].has_key('type'):
                col_params = params['collector']
                collector_val = JsonCollector(**col_params).resolve()
            else:
                Base.error("collector type is not supported.... yet!!!")
                pass

        if collector_val:
            ret_val = collector_val
        return ret_val

    def handle_variables(selfs, releaseId):
        self.persist_variables_to_release(releaseId)


    def persist_variables_to_release(self, releaseId):
        """
        Handles resolving the variables and injecting them into the template
        :return:
        """
        release = self.__releaseApi.getRelease(releaseId)

        self.set_variables_from_dict(self.resolve_xlr_template_variables(releaseId))

        Base.info("resolved profile:")
        print self.variables()

        # handle variables inside the release first

        newVariables = {}

        # printing the variables for reporting
        for k, v in self.variables().items():
            Base.info("key: %s \t value: %s \n" % (k, v))

        for key, value in self.variables().items():
            if re.match(self.__variable_start_regex, key) is None:
                key = "${%s}" % (key)
                if type(value) is dict:
                    value = self.resolve_variable(**value)
                if value == None:
                    Base.fatal("a value could not be generated for %s .. we are unable to keep the release valid" % key)
                    sys.exit(2)
                newVariables[key] = value
        release.setVariableValues(newVariables)
        self.__releaseApi.updateRelease(releaseId, release)

    def handle_toggles(self, releaseId):

        release = self.__releaseApi.getRelease(releaseId)

        if self.toggles:
            try:
                for t in self.toggles:
                    task = self.get_task_by_phase_and_title(str(t["phase"]), str(t["task"]), release)
                    if task:
                        Base.info("removing task %s " % task)
                        self.__repositoryService.delete(str(task))

                    else:
                        Base.info("task not found")
            except TypeError:
                Base.warning("toggles not valid... moving on")
        else:
            Base.warning("no toggles found")

    def get_phase_dict(self, release):
        phases = {}

        for p in release.phases:
            phases[str(p.title)] = p

        return phases

    def get_tasks_by_phase_dict(self, phase, release):
        tasks = {}
        for t in phase.tasks:
            tasks[str(t.title)] = t
        return tasks

    def get_tasks_for_phase_by_title(self, phaseTitle, release):

        phasedict = self.get_phase_dict(release)

        if phasedict.has_key(phaseTitle):
            return self.get_tasks_by_phase_dict(phasedict[phaseTitle], release)
        else:
            return False

    def get_task_by_phase_and_title(self, phaseTitle, taskTitle, release):
        tasks = self.get_tasks_for_phase_by_title(phaseTitle, release)
        if tasks:
            if tasks.has_key(taskTitle):
                return tasks[taskTitle]

        return False

    # template addition
    #
    #

    def find_ci_id(self, name, type):
        sp = SearchParameters()
        sp.setType(Type.valueOf(str(type)))

        for p in XLReleaseServiceHolder.getRepositoryService().listEntities(sp):
            if str(p.getTitle()) == name:
               return p

    def find_template_id_by_name(self, name):
        sp = SearchParameters()
        sp.setType(Type.valueOf(str('xlrelease.Release')))

        for p in XLReleaseServiceHolder.getRepositoryService().listEntities(sp):
            if p.isTemplate() == True:
                if str(p.getTitle()) == str(name):
                    Base.info("Found id: %s for name %s" % (str(p.getId()), name))
                    return str(p.getId())

        return None


    def create_phase(self, title, release):
        """
        creates a phase at the end of the release
        :param title: title of the phase
        :param release: the release id of THIS release
        :return: true/false
        """

        # danger close
        # generating a random number for the phaseid prefix
        randIdPost = random.randint(100000, 9999999)

        # get the template object from the repository service
        template = self.__repositoryService.read("/" + release.id)

        # get the phases object
        phases = template.getPhases()

        # get the id for the new phase

        # build the new pahse
        phase = PhaseBuilder.newPhase().withTitle(title) \
            .withId(template.getId() + "/Phase" + str(randIdPost)) \
            .withRelease(template) \
            .withStatus(PhaseStatus.PLANNED) \
            .build()

        # get the size of the phases object
        phaseIndex = len(phases)

        # we are always appending phases to the end of the release.. so the index will do
        phases.add(phaseIndex, phase)

        # save the phase
        phaseId = self.__repositoryService.create(phase)

        # save the release
        self.__repositoryService.update(template)

        return phaseId

    def createParallelTaskContainer(self, phaseId, release):

        taskType = Type.valueOf('xlrelease.ParallelGroup')

        task = taskType.descriptor.newInstance("nonamerequired")

        return self.__taskApi.addTask(str(self.get_target_phase(phaseId, release)), task)

    def createTaskContainer(self, phaseId, release,containerType="xlrelease.ParallelGroup", title = "Basic Container"):

        taskType = Type.valueOf(str(containerType))

        task = taskType.descriptor.newInstance("nonamerequired")
        task.setTitle(str(title))

        return self.__taskApi.addTask(str(self.get_target_phase(phaseId, release)), task)

    def createSimpleTaskInContainer(self, containerId, title, taskTypeValue,  propertyMap, parentTypeValue=None):

        parentTask = self.__taskApi.getTask(str(containerId))
        task = self.createSimpleTaskObject(taskTypeValue, title, propertyMap, parentTypeValue)
        task.setContainer(parentTask)
        self.__taskApi.addTask(str(containerId), task)

    def createSimpleTaskInPhase(self, phaseId, taskTypeValue, title, propertyMap):

        try:
            self.__taskApi.addTask(str(phaseId), self.createSimpleTaskObject(taskTypeValue, title, propertyMap))
        except:
            print "unable to create Task: %s in Phase: %s" % (title, phaseId)

    def createSimpleTaskObject(self, taskTypeValue, title, propertyMap={}, parentTypeValue = None ):
        """
        adds a custom task to a phase in the release
        :param phaseId: id of the phase
        :param taskTypeValue: type of task to add
        :param title: title of the task
        :param propertyMap: properties to add to the task
        :return:
        """



        if parentTypeValue == None:
            taskType = Type.valueOf(str(taskTypeValue))

            Task = taskType.descriptor.newInstance("nonamerequired")
            Task.setTitle(title)
            for item in propertyMap:

                if Task.hasProperty(item):
                    type = Task.getType()
                    desc = type.getDescriptor()
                    pd = desc.getPropertyDescriptor(item)

                    if str(pd.getKind()) == "CI":
                        Task.setProperty(item, self.find_ci_id(str(item), pd.getReferencedType()))
                    else:
                        Task.setProperty(item, propertyMap[item])

                else:
                    Base.info("dropped property: %s on %s because: not applicable" % (item, taskTypeValue))

            return Task


        else:
        # print propertyMap
            parenttaskType = Type.valueOf(str(parentTypeValue))

            parentTask = parenttaskType.descriptor.newInstance("nonamerequired")
            parentTask.setTitle(title)
            childTaskType = Type.valueOf(taskTypeValue)
            childTask = childTaskType.descriptor.newInstance("nonamerequired")
            for item in propertyMap:

                if childTask.hasProperty(item):
                    type = childTask.getType()
                    desc = type.getDescriptor()
                    pd = desc.getPropertyDescriptor(item)

                    if str(pd.getKind()) == "CI":
                        childTask.setProperty(item, self.find_ci_id(str(item), pd.getReferencedType()))
                    else:
                        childTask.setProperty(item, propertyMap[item])

                else:
                    Base.info("dropped property: %s on %s because: not applicable" % (item, taskTypeValue))
            parentTask.setPythonScript(childTask)

            return parentTask

    def createCustomScriptTask(self, phaseId, taskTypeValue, title, propertyMap, release, parentTypeValue = None):
        """
        adds a custom task to a phase in the release
        :param phaseId: id of the phase
        :param taskTypeValue: type of task to add
        :param title: title of the task
        :param propertyMap: properties to add to the task
        :return:
        """
        # print propertyMap

        if parentTypeValue == None:
            parentTypeValue = 'xlrelease.CustomScriptTask'

        phaseName = self.get_target_phase(phaseId, release)

        parenttaskType = Type.valueOf(parentTypeValue)

        parentTask = parenttaskType.descriptor.newInstance("nonamerequired")
        parentTask.setTitle(title)
        childTaskType = Type.valueOf(taskTypeValue)
        childTask = childTaskType.descriptor.newInstance("nonamerequired")
        vm = {}
        for item in propertyMap:
            Base.info("settings %s on task of type: %s" % (item, childTaskType))
            if childTask.hasProperty(item):
                 type = childTask.getType()
                 desc = type.getDescriptor()
                 pd   = desc.getPropertyDescriptor(item)


                 if str(pd.getKind()) == "CI":
                    childTask.setProperty(item, self.find_ci_id(str(item), pd.getReferencedType()))
                 else:
                    childTask.setProperty(item, propertyMap[item])
                 if str(pd.getCategory()) == "output":
                    Base.info("added %s to variable mapping" % propertyMap[item])
                    vm['%s.%s' % ("pythonScript", item)] = "${" + propertyMap[item] + "}"


            else:
                Base.info("dropped property: %s on %s because: not applicable" % (item, taskTypeValue))
        parentTask.setPythonScript(childTask)
        if parentTask.hasProperty('variableMapping'):
            parentTask.setVariableMapping(vm)

        self.__taskApi.addTask(str(phaseName), parentTask)


    def createSimpleTask(self, phaseId, taskTypeValue, title, propertyMap, release, parentTaskType):
        """
        adds a custom task to a phase in the release
        :param phaseId: id of the phase
        :param taskTypeValue: type of task to add
        :param title: title of the task
        :param propertyMap: properties to add to the task
        :return:
        """
        # print propertyMap

        Base.warning("createSimpleTask")



        phaseName = self.get_target_phase(phaseId, release)

        TaskType = Type.valueOf(taskTypeValue)
        Task = TaskType.descriptor.newInstance("nonamerequired")
        Task.setTitle(title)

        vm = {}
        for item in propertyMap:
            Base.info("settings %s on task of type: %s" % (item, TaskType))
            if Task.hasProperty(item):
                 type = Task.getType()
                 desc = type.getDescriptor()
                 pd   = desc.getPropertyDescriptor(item)

                 Base.warning(pd.getKind())
                 if item == "dependencies":
                    Base.info("dependencies found, these will be set later")
                 elif item == "templateId" and "Application" not in propertyMap[item]:
                     Task.setProperty(item, self.find_template_id_by_name(str(propertyMap[item])))
                 elif str(pd.getKind()) == "CI":
                    Task.setProperty(item, self.find_ci_id(str(item), pd.getReferencedType()))
                 elif str(pd.getKind()) == "bool":
                    if propertyMap[item] == "false":
                        Task.setProperty(item, False)
                    else:
                        Task.setProperty(item, True)
                 else:
                    Task.setProperty(item, propertyMap[item])


            else:
                Base.info("dropped property: %s on %s because: not applicable" % (item, taskTypeValue))

        

        print dir(Task.getType().getDescriptor().getPropertyDescriptor('templateVariables'))

        taskId = self.__taskApi.addTask(str(phaseName), Task)

        if propertyMap.has_key("dependencies"):

            for dep in propertyMap["dependencies"]:
                if dep.has_key("targetId"):
                    self.__taskApi.addDependency(str(taskId), dep["targetId"])
                if dep.has_key("target"):
                    self.__taskApi.addDependency(str(taskId), dep['target'])




    def phase_exists(self, targetPhase):
        phaseList = self.__phaseApi.searchPhasesByTitle(targetPhase, release.id)
        if len(phaseList) == 1:
            return True

        return False

    def get_target_phase(self, targetPhase, release):
        """
        search the release for the targetPhase by string name
        for some stupid reason we can't address it by its name ..

        :param targetPhase:string
        :return:phaseId
        """
        phaseList = self.__phaseApi.searchPhasesByTitle(str(targetPhase), release.id)

        if len(phaseList) == 1:

            return phaseList[0]
        else:

            print "Requested phase: %s not found. Creating it in the template first" % targetPhase
            self.create_phase(targetPhase, release)
            phaseList = self.__phaseApi.searchPhasesByTitle(str(targetPhase), release.id)
            if len(phaseList) == 1:
                return phaseList[0]
            else:
                Base.fatal(
                    "unable to create phase %s.. there is something seriously wrong with your installation" % str(
                        targetPhase))
                # should be replaced by some logic to create the phase

    def handle_phases(self, phasesDict, release):

        repeater = ""
        settings = self.settings()

        # loop over entry's
        for p in phasesDict:
            # if meta:repeat_on is set run a handle_phase for every one of the phases
            if p.has_key("meta") and p["meta"].has_key("repeat_on"):
                repeat_on = p["meta"]["repeat_on"]
                repeater = settings[repeat_on]

                # loop over the repeater and create the phases for it
                for r in repeater:
                    # get the settings ready for this
                    local_settings = settings
                    local_settings[repeat_on] = r

                    # handle the phase with the augmented settings
                    self.handle_phase(p, local_settings, release)
            else:
                self.handle_phase(p, settings, release)




    def handle_phase(self, phaseSettings, local_settings, release):

        # resolve the settings in the phaseDict by doing a variable search and replace on the phase dict.
        localPhaseDict = self.resolve_settings(phaseSettings, local_settings)



        # create the phase
        if localPhaseDict.has_key('title'):
            self.get_target_phase(localPhaseDict['title'], release)
            Base.info("phase: %s created with id %s" % (localPhaseDict['title'],localPhaseDict['title']))
        else:
            Base.error("phase: not created title could not be retrieved")

        if localPhaseDict.has_key('containers'):
            self.handle_containers(localPhaseDict['title'], localPhaseDict['containers'], local_settings, release)
        elif localPhaseDict.has_key('tasks'):
            self.handle_tasks(localPhaseDict['title'], localPhaseDict['tasks'], local_settings, release)
        else:
            Base.info("no task found for this phase")

    def handle_container(self, phaseId, containerDict, localSettings, release):
        '''
        handle a single container
        :param phaseId: id of the phase to add the containers to
        :param containerDict: dictionary containing all containers settings
        :param localSettings: settings to use
        :param release:
        :return:
        '''
        meta_dict = {"type" : "xlrelease.ParallelGroup", "title" : "default", "max_tasks" : 5}

        if containerDict.has_key('meta'):
            for k in meta_dict.keys():
                if containerDict['meta'].has_key(k):
                    print "metakey: %s value: %s" % (k, containerDict['meta'][k])
                    meta_dict[k] = containerDict['meta'][k]



        if containerDict.has_key('tasks'):

            for t in containerDict['tasks']:
                tasks_list = self.calculate_tasks_list(phaseId,containerDict['tasks'], localSettings, release)
            # split the list in acceptable chunks
            pprint.pprint(meta_dict)
            tasklists =  [tasks_list[x:x+int(meta_dict["max_tasks"])] for x in xrange(0, len(tasks_list), int(meta_dict["max_tasks"]))]


            # loop over the list of lists and do the thing
            #creating a container for each list
            x = 0
            for tl in tasklists:
                containerId = self.createTaskContainer(phaseId, release,containerType=meta_dict['type'], title=meta_dict['title'])

                for t in tl:
                    self.handle_task(t['phaseId'], t['taskDict'], t['task_local_settings'], t['release'], containerId)

    def handle_containers(self, phaseId, containersList, localSettings, release):
        '''
        handle a group of containers

        :param phaseId: id of the phase to add the containers to
        :param containersList: list of containers
        :param localSettings: settings to use to resolve any variables
        :param release: release to add the containers to
        :return:
        '''
        # loop over the containers

        for c in containersList:
            self.handle_container(phaseId, c, localSettings, release)


    def calculate_tasks_list(self, phaseId, tasksDict, tasksSettings, release):
        task_list = []
        repeater = ""

        for t in tasksDict:

            if t.has_key("meta") and t['meta'].has_key("repeat_on"):
                repeat_on = t['meta']['repeat_on']
                repeater = tasksSettings[repeat_on]

                for r in repeater:

                    task_local_settings = tasksSettings.copy()
                    task_local_settings[repeat_on] = r

                    task_list.append({"phaseId" : phaseId,"taskDict" : t, "task_local_settings" : task_local_settings,"release": release})

        return task_list

    def handle_tasks(self, phaseId, tasksDict, tasksSettings, release, containerId=None):
        '''
        handles a group of tasks
        :param phaseId: id of the phase to add the tasks to
        :param tasksDict: dictionary containing the task info
        :param tasksSettings: settings to use to resolve the variables in the tasksDict
        :param release: release to add the tasks to
        :param containerId: id of the container to add the tasks to if any
        :return: nothing
        '''
        repeater = ""

        for t in tasksDict:

            if t.has_key("meta") and t['meta'].has_key("repeat_on"):
                repeat_on = t['meta']['repeat_on']
                repeater = tasksSettings[repeat_on]

                for r in repeater:

                    task_local_settings = tasksSettings.copy()
                    task_local_settings[repeat_on] = r

                    self.handle_task(phaseId,t, task_local_settings, release, containerId)

            else:
                self.handle_task(phaseId, t, tasksSettings, release, containerId)

    def handle_task(self, phaseId, taskDict, taskSettings, release, containerId=None):
        '''
        handles a single task
        :param phaseId: id of the phase to add the task to
        :param taskDict: dictionary describing the task
        :param taskSettings:  settings to use when resolving variables in the inputdict
        :param release: release to add the steps to
        :param containerId: id of the container to add the task to if any
        :return: none
        '''
        localTaskDict = self.resolve_settings(taskDict, taskSettings)



        try:
            parentTypeValue = localTaskDict['meta']['parent_task_type']
            taskTitle = localTaskDict['title']
        except KeyError:
            parentTypeValue = None
            taskTitle = "forgot to set one"


        try:
            if containerId != None:
                if localTaskDict['meta']['task_type'] == "xlrelease.gateTask":
                    Base.Fatal("It is not allowed to create a gate task inside a container, failing")
                self.createSimpleTaskInContainer(containerId, taskTitle, localTaskDict['meta']['task_type'], localTaskDict, parentTypeValue)
            else:
                if parentTypeValue == None:
                    self.createSimpleTask(phaseId, localTaskDict['meta']['task_type'], taskTitle, localTaskDict, release, parentTypeValue)
                else:
                    self.createCustomScriptTask(phaseId, localTaskDict['meta']['task_type'], taskTitle, localTaskDict, release, parentTypeValue)

        except Exception as e:
            Base.warning(e.message)
            print "Unable to create task"


    def handle_template_plan(self, releaseId):
        '''
        handle the template plan .. add the steps described in the template to the plan in xlr
        :param releaseId: id of the release
        :return: nothing
        '''

        release = self.__releaseApi.getRelease(releaseId)



        self.set_template_plan_from_dict(self.resolve_xlr_template_variables_in_settings(self.template_plan(), releaseId))

        if self.template_plan():
            self.handle_phases(self.template_plan()["phases"], release)

    ### utility functions






    def resolve_settings(self, inputDict, inputSettings):
        '''
        scan the inputDict for variable markers and look for resolution in the settings section of the template
        :param inputDict: Dictionary to scan
        :param inputSettings: settings that pertain to this input dictionary
        :return: dictionary with resolution information
        '''

        vars_list = []
        resolve_dict = {}
        output_dict = {}

        if inputSettings != None:
            # find all the variables in the target dictionary
            for k, v in inputDict.items():
                if isinstance(v, unicode) or isinstance(v, str):
                    x = self.find_all_variables(str(v))
                    if x:
                        vars_list = vars_list + list(set(x) - set(vars_list))


            # loop over the list with found variables
            for v in vars_list:
                # check if we can find a resolution in the settings for this app
                if inputSettings.has_key(v):
                    # if we find a list in settings for this variable concatenate and dump
                    if type(inputSettings[v]) is list:
                        resolve_dict[v] = ",".join(inputSettings[v])
                    else:
                        resolve_dict[v] = inputSettings[v]

            # loop over the resolve_dict and check it for stuff that could trigger a more specific set of variables
            if inputSettings.has_key('specific_settings'):
                specific_dict = inputSettings['specific_settings']
                for k, v in resolve_dict.items():
                    if specific_dict.has_key(k):
                        if specific_dict[k].has_key(v):
                            resolve_dict.update(specific_dict[k][v])

            # do one last loop over the dictionaries non list/dict objects and replace the placeholders/variables with te result
            for k, v in inputDict.items():
                if isinstance(v, unicode) or isinstance(v, str):
                    # loop over the keys of the resolve dict
                    for s in resolve_dict.keys():
                        ps = self.__variable_start_string + str(s) + self.__variable_end_string

                        v = v.replace(ps, resolve_dict[s])

                output_dict[k] = v

            for k, v in output_dict.items():
                Base.info("Key: %s resolved to: %s" % (k, v))

            return output_dict
        else:
            return inputDict

    def find_all_variables(self, string):
        o = 0
        output = []
        while True:
            s = self.find_variable_start(string, o)
            if s != False:
                e = self.find_variable_end(string, s)
                if e == False:
                    break
                else:
                    o = e
                    Base.info("found variable %s in %s" % (string[s:e], string))
                    output.append(string[s:e])
                    continue
            else:
                break
        if len(output) == 0:
            Base.info("no variable found in %s" % string)
            return False
        return output

    def find_variable_start(self, s, offset):
        try:
            return s.index(self.__variable_start_string, offset) + 2
        except ValueError:
            return False

    def find_variable_end(self, s, start_pos):
        try:
            return s.index(self.__variable_end_string, start_pos)
        except ValueError:
            return False


    def resolve_xlr_template_variables_in_settings(self, input_object, release_id):
        '''
        resolve xlr variables in dictionaries
        :param release_id:
        :param input_dictionary:
        :return:
        '''


        output_list = []
        output_dict = {}

        # step through the dictionary
        if type(input_object) == str or type(input_object) == unicode:
            if '${' in input_object:
                 Base.info("found variable in %s" % input_object)
                 input_object = self.replace_xlr_variable_in_string(input_object, release_id)
            return input_object


        if isinstance(input_object, dict):
            for k,v in input_object.items():
                output_dict[k] = self.resolve_xlr_template_variables_in_settings(v, release_id)
            return output_dict
        if isinstance(input_object, list):
            for v in input_object:
                output_list.append(self.resolve_xlr_template_variables_in_settings(v, release_id))
            return output_list


    def replace_xlr_variable_in_string(self, input_string, release_id):

        xlr_variables = self.get_release_variables(release_id)
        pprint.pprint(xlr_variables)
        for x, y in xlr_variables.items():
            if x in input_string and y != "":
                Base.info("replacing variable %s with value %s" % (x, y))
                input_string = input_string.replace(x, y)

        return input_string


    def handle_template(self, releaseId):

        if self.template_plan() == None:
            Base.fatal("no template plan found.. we can't continue")
        if self.variables() != None:
            self.handle_variables(releaseId)
        if self.settings() != None:
            self.set_settings_from_dict(self.resolve_xlr_template_variables_in_settings(self.settings(), releaseId))
        if self.template_plan():
            self.handle_template_plan(releaseId)

