## Install basic packages

```bash
sudo apt update
sudo apt upgrade
```

```bash
sudo apt install git npm
```

## Clone repo

```bash
git clone https://github.com/GitHubDanya/mmildeum.git
cd mmildeum
```

## Frontend setup

### Install latest version of node.js

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
```

### Install npm packages

```bash
cd mmildeum/frontend
npm install
```

### Set up .env file

`/mmildeum/frontend/.env:`
```bash
VITE_CESIUM_ION_TOKEN=your cesium token
VITE_API_BASE_URL=/api
```

## Backend setup

### Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

## Run

```bash
cd ../
make dev
```

First run will be exceptionally long because the api has to fetch relative data files.


After setup, webpage should be accessible at `http://localhost:5173`
