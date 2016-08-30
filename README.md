#XL Release variable persistence off plugin

## Preface
This document descripts the functionality provide by the `xlr-release-profile-plugin`, as well as potential future functionality.

## Overview
This module enables users of xl-release to store release lay-outs and variables outside of xlr.
Plus it does all kinds of funky variable management stuff.

## Installation


Copy the plugin JAR file into the `SERVER_HOME/plugins` directory of XL Release.

### Limitations

### Supported Tasks

* `LoadProfile` **deprecated**
* `MakeVariableOptional`
* `SetDefaultValue`
* `LoadDynamicProfile`
* `OverwriteVariable`
* `LoadProfileFromUrl` **deprecated**
* `LoadTemplateProfile`
* `SetReleaseCounter`
* `SetReleaseCounterString`
* `IncrementReleaseCounter`
* `GetReleaseCounter`
* `CreateCounterStore`
* `DestroyCounterStore`


### configuration items
* `ReleaseProfile` **deprecated**
* `ReleaseCounterStore`

### triggers
* `jsonTrigger`


### Task documentation

####  MakeVariableOptional
* `Description`: make a variable optional, this makes a variable that would otherwise be required for a release to start not be required so that we are able to fill it at a later time.
* `Input Properties`:
  * `variableName`: name of the variable to make optional
* `Output properties`: **N/A**

####  SetDefaultValue
* `Description`: Set a variable to a default value in the template plan.
* `Input Properties`:
  * `variableName`: name of the variable to make optional
  * `defaultValue`: default value to apply to the variable
* `Output properties`: **N/A**

####  LoadDynamicProfile
* `Description`: load a variable profile from any location. This function is deprecated and will soon be replaced by loadTemplateProfile.
* `Input Properties`:
  * `profileUrl`: http/https url pointing at the profile (json format)
  * `profiles`: __deprecated__ inline profile (for testing purposes only)
  * `profileFromRepository`: reads a __ReleaseProfile__ from the internal configuration
* `Output properties`: **N/A**

####  OverwriteVariable
* `Description`: Overwrite a variable in the release (hard low-level overwrite)
* `Input Properties`:
  * `variableName`: name of the variable overwrite
  * `overwriteValue`: value to change the variable to. If this field is a string None this task wil not do anything
* `Output properties`: **N/A**

####  loadTemplateProfile
* `Description`: Load a release template profile
* `Input Properties`:
  * `profileUrl`: url to download the profile from. Multiple profiles can be specified by using a semicolon seperated list of urls (url;url)
  * `profile`: inline profile to load __Development testing purposes__
* `Output properties`: **N/A**

####  SetReleaseCounter
* `Description`: Set a release counter in a counterstore. Counter stores are used to transmit data and variable vaules between seperate releases
* `Input Properties`:
  * `counterStore`: name of the **ReleaseCounterStore** `store to use
  * `counterName`: name of the counter to set
  * `counterValue`: value of the counter to set
* `Output properties`: **N/A**

####  SetReleaseCounterString
* `Description`: Set a release counter to a string value in a counterstore. this counter can then no longer be used with incrementCounterstore Counter stores are used to transmit data and variable vaules between seperate releases
* `Input Properties`:
  * `counterStore`: name of the **ReleaseCounterStore** `store to use
  * `counterName`: name of the counter to set
  * `counterValue`: value of the counter to set (string value)
* `Output properties`: **N/A**


####  incrementReleaseCounter
* `Description`: increment an integer formatted counter in a counterstore. Counter stores are used to transmit data and variable vaules between seperate releases
* `Input Properties`:
  * `counterStore`: name of the **ReleaseCounterStore** `store to use
  * `counterName`: name of the counter to increment
* `Output properties`:
  * `outputVariable`: name of the variable to store the incremented counter in

####  getReleaseCounter
* `Description`: retrieve a value from a counterStore
* `Input Properties`:
  * `counterStore`: name of the **ReleaseCounterStore** `store to use
  * `counterName`: name of the counter to retrieve
* `Output properties`:
  * `outputVariable`: name of the variable to store the retrieved counter in

####  createCounterStore
* `Description`: Create a counter store in the XL-Release configuration
* `Input Properties`:
  * `counterStore`: name of the **ReleaseCounterStore** `store to create
* `Output properties`: **N/A**

####  destroyCounterStore
* `Description`:  Destroy a counter store in the XL-Release configuration
* `Input Properties`:
  * `counterStore`: name of the **ReleaseCounterStore** `store to destroy
* `Output properties`: **N/A**


### Configuration Items documentation

#### ReleaseProfile **deprecated**
* This ci is deprecated and will be removed in future versions

#### ReleaseCounterStore

* `Description`:  A entity to store release counters in json format inside the xlr repository
* `Properties`:
  * `counterStorage`: a string value that holds the json formatted counter store
  * `modTime`: time of last modification`: this field is not te be editted by hand and serves as a field used in the locking mechanism

### Triggers Documentation

#### jsonTrigger

* `Description`: a trigger that scans a url that returns json for possible changes. it takes a url and a json path .
    If the json data returned by the url changed after the last time this trigger ran at the point indicated by the json path the trigger will start the release.
* `Properties`:
    * `url`: full url that retrieves the url to be used with the jsonpath
    * `jsonPath`: path to use when examining the json
      



## Example Use Case

### profile templates
Profile templates are a way of storing everything you need to run a release in an external store like artifactory/amazon s3/github
The templates can be retrieved by using either the LoadDynamicProfile (variables only) or the LoadTemplateProfile(variables/templateplan) tasks.


#### Variable profile
A variable profile is able to retrieve variables from remote sources .

This is an example of a variable profile:
```
{"variables"`:
    {"test1"`: { "default_value" `: "555",
                "collector" `: { "type" `: "json" ,
                                "url" `: "http`://192.168.99.100`:32768/artifactory/xlrelease/collector_test.json",
                                "path" `: "claims/bpm/2012_02/buildNr" }},
     "test2"`: { "default_value" `: "444",
                "collector" `: { "type" `: "json" ,
                                "url" `: "http`://192.168.99.100`:32768/artifactory/api/storage/xlrelease?properties",
                                "path" `: "properties/latest_build" }},
     "test3"`: "scarecrow" }
     ,"toggles" `:
      [{"phase" `: "deploy_to_dev", "task" `: "shitty", "skip" `: "true"},
       {"phase" `: "deploy_to_dev", "task" `: "shitty1", "skip" `: "true"}]
     ,"tasks"`: {}}
```

Explanation:
    * `variables`: indicates that this is the variables part of a template
    * `test1` : this is the name of the variable as it will be availeble in xlr
        * `default_value`: the default value for the variable is it is not resolvable in any other way
        * `collector`: this describes the collection method for the variable
            * `type`: what type of collector is this (available collectors: json)
            * `url`: url to use to collect the json the extract the variable value from (mandetory for json collector)
            * `path`: path to take in the json data: when multiple results are found the first one is used

### Template plan

#### Settings
```
{
  "settings": {
    "appName": [
      "test1",
      "test2",
      "test3"
    ],
    "environment": [
      "dev",
      "test",
      "ua"
    ],
    "notificationGroup" : "wvos@xebia.com",
    "stream" : "c",
    "portfolio": "claims",
    "release": "2016_01",
    "build_template": "WASLP_BUILD",
    "deployment_template": "WASLP_DEPLOY"
  },
```

#### template plan
```
"template_plan": {
    "phases": [
      {
        "title": "initialization",
        "tasks": [
          {
            "meta": {
              "task_type": "rel.SetDefaultValue",
              "parent_task_type": "xlrelease.CustomScriptTask"
            },
            "title": "set default notification group",
            "variableName": "notificationGroup",
            "defaultValue": "${notificationGroup}"
          },
          {
            "meta": {
              "task_type": "rel.incrementReleaseCounter",
              "parent_task_type": "xlrelease.CustomScriptTask"
            },
            "title": "Set release serial",
            "counterStore": "release_serial_nr_store",
            "counterName": "$<portfolio>_orchestrator_serialNr",
            "outputVariable": "releaseSerialNr"
          },
          {
            "meta": {
              "task_type": "rel.createCounterStore",
              "parent_task_type": "xlrelease.CustomScriptTask"
            },
            "title" : "create counter store",
            "counterStore": "$<portfolio>_$<release>_${releaseSerialNr}"
          }
        ]
      },
      {
        "title": "build dar package(s)",
        "tasks": [
          {
            "meta": {
              "repeat_on": "appName",
              "task_type": "xlr.CreateAndStartSubRelease",
              "parent_task_type": "xlrelease.CustomScriptTask"
            },
            "title": "$<appName> Build",
            "xlrServer": "local",
            "username": "admin",
            "templateName": "$<build_template>",
            "releaseTitle": "Build $<appName>",
            "releaseDescription": "Build $<appName>",
            "variables": "release=$<release>,portfolio=$<portfolio>,appName=$<appName>,buildNr=dummy,darProfileLocation=dp_$<portfolio>_$<appName>.json,releaseSerialNr=${releaseSerialNr},notificationGroup=$<notificationGroup>",
            "asynch": "false"
          }
        ]
      },
      {
        "title": "deploy dar package to $<environment>",
        "meta": {
          "repeat_on": "environment"
        },
        "containers": [
          {
            "tasks": [
              {
                "meta": {
                  "repeat_on": "appName",
                  "task_type": "xlr.CreateAndStartSubRelease",
                  "parent_task_type": "xlrelease.CustomScriptTask"
                },
                "title": "$<appName> deploy",
                "xlrServer": "local",
                "username": "admin",
                "templateName": "$<deployment_template>",
                "releaseTitle": "Deploy $<appName> to $<environment>",
                "releaseDescription": "Deploy $<appName> to $<environment>",
                "variables": "buildNr=dummy,portfolio=$<portfolio>,appName=$<appName>,release=$<release>,environment=$<environment>_$<stream>,releaseSerialNr=${releaseSerialNr},notificationGroup=$<notificationGroup>"
              }
            ]
          }
        ]
      },
      {
        "title": "cleanup",
        "tasks" : [
          {
            "meta": {
              "task_type": "rel.destroyCounterStore",
              "parent_task_type": "xlrelease.CustomScriptTask"
            },
            "title" : "destroy counter store",
            "counterStore": "$<portfolio>_$<release>_${releaseSerialNr}"
          }
        ]
      }
    ]
  }
  ```
