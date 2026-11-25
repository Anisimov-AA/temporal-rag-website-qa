# Temporal RAG for a credit union website

A chatbot that answers member questions from 5 dated downloads of a credit union website. It picks the right download for "now" or "as of" questions, puts the newest facts first, cites its sources, and says "I don't know" when the site does not say.

The task is in [TASK.md](TASK.md).

## What is in this repo

1. **The submission:** `solution/`. A `build()` that returns an object with `ingest`, `answer` and `conflicts`, as the task asks. The version I handed in has the tag `submission`.
2. **The docs:** [the experiments map](https://anisimov-aa.github.io/temporal-rag-website-qa/config.html). Every step I tried, with its results and the answers. From there every part of the chain has its own page with real examples.
3. **A page to ask by hand:** `demo/`. I made it to read answers next to their sources and kept it in case it helps. Each source opens the saved copy of the page at the passage the model read.
4. **Pages to read the data by eye:** `dev/views/`. What the cleaning removes from each page and how each page is cut into chunks.

## What it needs

One NVIDIA GPU with 24 GB of memory. No API and no API keys: all models run locally.

- Gemma 4 26B A4B, 4-bit, in Ollama: writes the answer
- bge-m3 in Ollama: turns the text into vectors for the search
- bge-reranker-v2-m3 (Hugging Face, fp16): reranks the search results

I had no paid API and no GPU of my own, so I rented one NVIDIA L4 on Google Cloud. Any cloud or computer with a 24 GB NVIDIA GPU works the same way.

## Score it with your own questions

The solution plugs into the kit's scorer as is. It only needs to know where Ollama runs.

**1. Ollama with the two models.** Install it from [ollama.com/download/linux](https://ollama.com/download/linux), then:

    OLLAMA_FLASH_ATTENTION=1 OLLAMA_MAX_LOADED_MODELS=2 OLLAMA_KEEP_ALIVE=-1 ollama serve &
    ollama pull bge-m3
    ollama pull gemma4:26b-a4b-it-q4_K_M

**2. Python 3.11 and the packages:**

    git clone https://github.com/Anisimov-AA/temporal-rag-website-qa.git
    cd temporal-rag-website-qa
    curl -LsSf https://astral.sh/uv/install.sh | sh
    uv venv --python 3.11 && source .venv/bin/activate
    uv pip install torch --index-url https://download.pytorch.org/whl/cu128
    uv pip install -r requirements.txt

**3. Where Ollama is.** A `.env` file in the top folder (or the same environment variable):

    GCP_OLLAMA=http://localhost:11434

**4. The data.** The website downloads are not in this repo. Put the 5 zips from the kit into `snapshots_zip/`; the scorer unpacks them.

**5. Run the scorer** with any question file in the kit's format:

    python harness/run_eval.py --submission solution --eval eval/public_eval.jsonl

- The first run builds one search index per download: about 5 minutes. Later runs reuse it from `index/`.
- An answer takes about 3–8 seconds on an L4.
- The score and every answer go to `results/`.

## Run it on Google Cloud (what I did)

**1. A VM with an L4.** Compute Engine → Create instance: machine type `g2-standard-8` (8 vCPU, 32 GB RAM, 1 L4), boot disk with the NVIDIA driver (I used `common-cu129-ubuntu-2204-nvidia-580`), 100 GB. Open SSH and check the GPU:

    nvidia-smi

**2. Open port 7860** for the demo page. VPC network → Firewall → Create firewall rule: all instances, source `0.0.0.0/0`, TCP `7860`.

**3. Docker with access to the GPU:**

    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker $USER
    newgrp docker

    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
    docker run --rm --gpus all ubuntu nvidia-smi

**4. The code and the data.** "Upload file" in the SSH window puts the 5 zips in your home folder:

    git clone https://github.com/Anisimov-AA/temporal-rag-website-qa.git
    cd temporal-rag-website-qa
    sudo apt-get install -y unzip
    mkdir -p snapshots_zip && mv ~/*.zip snapshots_zip/
    for z in snapshots_zip/*.zip; do unzip -q -n "$z" -d snapshots/; done

**5. Start Ollama and the demo page:**

    cd demo
    docker compose up -d --build
    docker compose logs -f app

The first start takes about 20 minutes: the image, the models (18 GB) and the index. It is ready at `Uvicorn running on http://0.0.0.0:7860`. Open `http://<the VM's External IP>:7860`.

**6. The scorer on the same VM.** Stop the demo page first: both load the reranker, and two copies do not fit on one L4 next to Gemma.

    docker compose stop app
    mkdir -p gcp_results
    nohup docker compose run --rm -v "$PWD/../eval:/app/eval" -v "$PWD/gcp_results:/app/results" app python harness/run_eval.py --submission solution --eval eval/full_eval.jsonl --repeat-sample 40 --out results/gcp > gcp.log 2>&1 &
    tail -3 gcp.log

The report lands in `demo/gcp_results/gcp/`. Then start the demo again: `docker compose start app`.

**7. Stop the VM when you are done.** The GPU costs money while it runs. The models and the index stay on the disk, so the next start takes a few minutes (`docker compose up -d`). To keep the same address, make the External IP static (VPC network → IP addresses).

## Read the data by eye

With the data in `snapshots/` and the packages installed:

    python dev/views/view_clean.py
    python dev/views/view_chunks.py

They write `view_clean.html` and `view_chunks.html` with one page per website page into `dev/views/out/`. This folder stays out of git, because it holds the website's text.

## Results

On one L4 on Google Cloud, on the 40 public questions plus 80 reworded ones:

- accuracy 0.770 (0.841 without the 3 broken answer keys)
- the same answer on a repeat: 0.89 (the same without the broken keys)
- p95 answer time 7.5 s (the same without the broken keys)
- final score 0.713 (0.779 without the broken keys)

The final score counts accuracy, repeats and speed. The kit has no answer key for conflicts, so that part is left out.

## Data

The data is a real credit union's public website, shared for the hackathon only. It is not in this repo.
