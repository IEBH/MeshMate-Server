# containerised_mesh_suggester

## Description
This repo has been modified from the original repo of Shuai Wang (Daylan) for MeSH Suggester. 
https://github.com/wshuai190/MeSH_Suggester_Server

Four current methods are available in this repo: Semantic-BERT, Fragment-BERT, Atomic-BERT and ATM. We dockerize the application and service to simplify their running in different environments. In containerization, we split the application and service into two images according to the frontend web application (`client`) and a backend API service (`server`). Technically, you may need to run only the server container to serve suggestions via API for your application. Running both is for testing the suggestions and noticing how to use the API.

The server is served at port 5000 in current containers, whereas the client is at port 80.

## Server Requirement
We tested these containers on a single AWS EC2 m7i.large, which comes with the following specifications.
* vCPU 2
* Memory 8 GB
* Storage 80 GB

We also tried to run the server container on the GPU instance g4dn.xlarge, but it does not take any benefits from the available GPU as the original code uses faiss_cpu.
  
## How to run

### Step 1: Clone this git repo
Importantly note that you must install git lfs before performing git clone; otherwise, the data used by this repo will be not be cloned or pulled to your local machine.

`git clone [https url]`

Example

`git clone https://github.com/kimmlee/Containerised_MeSH.git`

or 

`git clone https://[Personal Access Token - PAT]@github.com/kimmlee/Containerised_MeSH.git`

  
### Step 2: Build dockerfile into docker image (run only once at the first time)
`cd Containerised_MeSH`

`docker compose build`


### Step 3: Create/start service as a container(s) from a docker image(s)

#### Case I: Run frontend and backend together
`docker compose up -d`

#### Case II: Run backend only 
`docker compose up -d server`

------------------------------------------------------------------------------------------------------------------

## How to stop

### Use one of the options to stop containers according to a development purpose
 1. Stop running containers without removing them (no change in an env file.)
    
`docker compose stop`

You can either select to stop a particular sevice only.

`docker compose stop client`

2. Stop and remove containers (there is a change in an env file.)

`docker compose down`

3. Stop and remove containers and destroy the container images in case you want to rebuild the images

`docker compose down --rmi all`
