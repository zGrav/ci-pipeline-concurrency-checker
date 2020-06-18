import os
import time

from sys import exit

from urllib.parse import urlparse
from gitlab import Gitlab

# sleep params
FULL_CYCLE_SLEEP = 300  # 5m
SECONDARY_CYCLE_SLEEP = 60  # 1m

# TODO: 'service' account?
# currently using personal access token

# handles gitlab specific stuff, url/token/project_id
# CI_PROJECT_URL = http(s)://gitlab_url_here/
# ACCESS_TOKEN should be created in:
# https://gitlab_url_here/profile/personal_access_tokens
# CI_PROJECT_ID = Settings -> General

URL = urlparse(os.getenv("CI_PROJECT_URL"))

gl = Gitlab(URL.scheme + "://" + URL.netloc,
            private_token=os.getenv("ACCESS_TOKEN"))

project = gl.projects.get(os.getenv("CI_PROJECT_ID"))

print("Grabbing project with ID: {}".format(
    os.getenv("CI_PROJECT_ID")), flush=True)


def checkAndCancelIfNeeded():
    # cancels self or other pipelines if needed :)

    # gets name of branch being deployed
    branchName = os.getenv('CI_COMMIT_REF_NAME')

    # filters the entire pipeline list
    # for specific branchName
    # this list is paginated,
    # so limited to 20 results according to docs
    # https://python-gitlab.readthedocs.io/en/stable/gl_objects/pipelines_and_jobs.html?highlight=pipeline#project-pipelines
    result = [pipe for pipe in project.pipelines.list() if pipe.ref ==
              branchName]

    # gets current commit SHA hash
    selfSHA = os.getenv('CI_COMMIT_SHA')

    # gets where we are in the filtered array
    index = next((i for i, item in enumerate(result)
                  if item.sha == selfSHA), -1)

    if index == -1:
        print('i\'m very old and out of scope, cancelling myself and exiting cleanly.', flush=True)
        pl = project.pipelines.get(result[index].id)
        pl.cancel()
        exit(0)

    # and if we're not the first one, we cancel ourselves!
    if index != 0 and index != -1:
        print('i\'m old, cancelling myself and exiting cleanly.', flush=True)
        pl = project.pipelines.get(result[index].id)
        pl.cancel()
        exit(0)
    elif index == 0 and index != -1:
        # if we are actually 0 we look for other pipes
        # currently running/scheduled and if found,
        # we cancel them.
        result = [pipe for pipe in result if pipe.attributes['sha'] != selfSHA and pipe.attributes['status']
                  == 'running' or pipe.attributes['status'] == 'pending']

        for pipe in result:
            print("Cancelling pipeline with id: {}".format(pipe.id), flush=True)
            pl = project.pipelines.get(pipe.id)
            pl.cancel()
            # small wait for all the potential pipeline cancels
            time.sleep(1)


# we check if should cancel ourselves
# or older pipes first :)
checkAndCancelIfNeeded()

# refresh the project
project = gl.projects.get(os.getenv("CI_PROJECT_ID"))


def isThereAnotherPipeRunning():
    # refresh the project
    project = gl.projects.get(os.getenv("CI_PROJECT_ID"))

    # initiate counter for running pipes
    add = 0

    # initiate counter for waiting pipes
    wait = 0

    # gets all running pipelines
    # that are not self
    # and are running
    # or pending
    result = [pipe for pipe in project.pipelines.list(
    ) if pipe.attributes['status'] == 'running' or pipe.attributes['status'] == 'pending']

    # we grab each pipeline
    for pipe in result:
        # get this pipe jobs
        jobs = pipe.jobs.list()

        for job in jobs:
            if job.stage == "check_if_building" and job.status == 'running':
                wait = wait + 1
            elif job.status == "running":
                add = add + 1

    if wait == 0 and add == 0:
        print("Nothing found, moving on", flush=True)
        return False

    if wait > 0 and add == 0:
        print("Only found waiting pipes, checking if it's time", flush=True)

        # gets current commit SHA hash
        selfSHA = os.getenv('CI_COMMIT_SHA')

        result = [pipe for pipe in project.pipelines.list(
        ) if pipe.attributes['status'] == 'running' or pipe.attributes['status'] == 'pending']

        waitItems = []

        # we grab each pipeline
        for pipe in result:
            # get this pipe jobs
            jobs = pipe.jobs.list()

            for job in jobs:
                if job.stage == "check_if_building" and job.status == 'running':
                    waitItems.append(job)

        # gets where we are in the filtered array
        index = -1

        for idx, item in enumerate(waitItems):
            if item.pipeline['sha'] == selfSHA:
                index = idx
                break

        # if we are the last item of the array
        # it's our turn to build
        if index == (len(waitItems) - 1) and index != -1:
            print(
                "I'm the last entry on the waitItems list, time for me to shine and build", flush=True)
            return False
        else:
            print("Not my time just yet", flush=True)
            return True

    return add > 1


didWeSleepFullCycle = False
firstSecondCycleMessage = True

while isThereAnotherPipeRunning():
    # refresh the project
    project = gl.projects.get(os.getenv("CI_PROJECT_ID"))

    # if we found a pipe running,
    # we recheck if we need to cancel
    # ourselves or others
    checkAndCancelIfNeeded()

    if didWeSleepFullCycle != True:
        # if we didn't go through FULL_CYCLE_SLEEP,
        # we do it
        print(
            "A pipe is running, waiting for {:.0f} minutes since it's the average build time!".format(FULL_CYCLE_SLEEP / 60), flush=True)
        time.sleep(FULL_CYCLE_SLEEP)
        didWeSleepFullCycle = True
    else:
        # otherwise, we step down to SECONDARY_CYCLE_SLEEP
        if firstSecondCycleMessage == True:
            format_list = [FULL_CYCLE_SLEEP / 60, SECONDARY_CYCLE_SLEEP / 60]
            print("{:.0f} minutes have elapsed. Waiting for {:.0f} minute from now on.".format(
                *format_list), flush=True)
            firstSecondCycleMessage = False

        print("A pipeline is still running...", flush=True)
        time.sleep(SECONDARY_CYCLE_SLEEP)

print("No pipelines found running, will execute this pipeline now :)", flush=True)
exit(0)
