# Temporal RAG for a credit union website

A chatbot that answers member questions from 5 dated downloads of a credit union website. It picks the right download for "now" or "as of" questions, puts the newest facts first, cites its sources, and says "I don't know" when the site does not say.

**Experiments:** [the map of every step I tried and its results](https://anisimov-aa.github.io/temporal-rag-website-qa/config.html). The pipeline pages and the answers pages open from there.

The task is in [TASK.md](TASK.md).

## What it runs on

Everything runs on one NVIDIA GPU with 24 GB of memory. There are no API calls and no API keys.

- Gemma 4 26B A4B, 4-bit, in Ollama: writes the answer
- bge-m3 in Ollama: builds the search index
- bge-reranker-v2-m3 (Hugging Face, fp16): reranks the search results

I had no paid API and no GPU of my own, so I rented one NVIDIA L4 on Google Cloud. Any cloud or computer with a 24 GB NVIDIA GPU works the same way.

## The demo

`demo/` is a web page on top of the same chain. You ask a question, pick a version of the site, and get the answer with its sources. Each source opens the saved copy of the page at the passage the model read. The demo runs in Docker: Ollama with the two models, and the app on port 7860.

## Run it on Google Cloud (what I did)

**1. A VM with an L4.** Compute Engine → Create instance:

- machine type `g2-standard-8` (8 vCPU, 32 GB RAM, 1 NVIDIA L4)
- boot disk: a Deep Learning image with the NVIDIA driver (I used `common-cu129-ubuntu-2204-nvidia-580`), 100 GB

Open SSH on the VM and check that the driver sees the GPU:

    nvidia-smi

**2. Open port 7860.** VPC network → Firewall → Create firewall rule: targets "All instances in the network", source `0.0.0.0/0`, TCP `7860`.

**3. Docker and its access to the GPU.**

    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker $USER
    newgrp docker

    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker

Check that a container sees the GPU:

    docker run --rm --gpus all ubuntu nvidia-smi

**4. The code and the data.** The website downloads are not in this repo: take the 5 zips from `snapshots_zip/` of the hackathon kit. In the SSH window, "Upload file" puts them in your home folder.

    git clone https://github.com/Anisimov-AA/temporal-rag-website-qa.git
    cd temporal-rag-website-qa
    sudo apt-get install -y unzip
    mkdir -p snapshots_zip && mv ~/*.zip snapshots_zip/
    for z in snapshots_zip/*.zip; do unzip -q -n "$z" -d snapshots/; done

**5. Start the demo.**

    cd demo
    docker compose up -d --build
    docker compose logs -f app

The first start takes about 20 minutes: it builds the image, pulls the models (18 GB) and builds the index (5 min). It is ready at `Uvicorn running on http://0.0.0.0:7860`. Open `http://<the VM's External IP>:7860`.

**6. The scorer on the same machine.** It runs inside the app container, which already has the code, the data, the index and Ollama:

    docker compose cp ../eval app:/app/eval
    docker compose exec app mkdir -p results
    docker compose exec -d app sh -c "python harness/run_eval.py --submission solution --eval eval/full_eval.jsonl --repeat-sample 40 --out results/gcp > results/gcp.log 2>&1"
    docker compose exec app tail -3 results/gcp.log

When it ends, copy the report out:

    docker compose cp app:/app/results/gcp ./gcp_results

**7. Stop the VM when you are done.** The GPU costs money while the VM runs. The models and the index stay on the disk, so the next start takes a few minutes:

    cd ~/temporal-rag-website-qa/demo && docker compose up -d

To keep the same address, make the External IP static (VPC network → IP addresses → Promote to static).

## Other clouds or your own GPU

Any Linux machine with a 24 GB NVIDIA GPU and its driver works. With Docker, start from step 3.

Without Docker (for example on a cluster node without sudo):

1. Install [Ollama](https://ollama.com/download/linux), start it and pull the two models:

       OLLAMA_FLASH_ATTENTION=1 OLLAMA_MAX_LOADED_MODELS=2 OLLAMA_KEEP_ALIVE=-1 ollama serve &
       ollama pull bge-m3
       ollama pull gemma4:26b-a4b-it-q4_K_M

2. Install Python 3.11 and the packages:

       curl -LsSf https://astral.sh/uv/install.sh | sh
       uv venv --python 3.11 && source .venv/bin/activate
       uv pip install torch --index-url https://download.pytorch.org/whl/cu128
       uv pip install -r requirements.txt

3. Put the 5 zips into `snapshots_zip/` (the scorer unpacks them) and tell the solution where Ollama is, in a `.env` file:

       GCP_OLLAMA=http://localhost:11434

4. Run the scorer:

       python harness/run_eval.py --submission solution --eval eval/public_eval.jsonl

## Results

On one L4, on the 40 public questions plus 80 reworded ones:

- accuracy 0.767 (0.839 without the 3 broken answer keys)
- the same answer on a repeat: 0.89 (the same without the broken keys)
- p95 answer time 8 s (the same without the broken keys)
- final score 0.707 (0.773 without the broken keys)

The final score counts accuracy, repeats and speed. The kit has no answer key for conflicts, so that part is left out.

## Data

The data is a real credit union's public website, shared for the hackathon only. It is not in this repo.
