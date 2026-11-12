# Setting up Alyos Hive on Windows

## 1. Install Python

Download Python 3.10 or newer from [python.org](https://www.python.org/downloads/windows/). In the installer, tick **"Add python.exe to PATH"**.

Check it in PowerShell:

```powershell
python --version
```

## 2. Get the hive

```powershell
cd C:\
git clone https://github.com/YoussefCreate/alyos-hive.git
cd alyos-hive
python -m hive init
python -m hive run --backend mock
```

No Git? On the GitHub page click **Code → Download ZIP**, unzip it to `C:\alyos-hive`, and run the same commands from that folder.

## 3. Choose a brain

### Local and free: Ollama

1. Install from [ollama.com/download](https://ollama.com/download).
2. Pull a model:
   ```powershell
   ollama pull llama3.1:8b
   ```
3. Run the hive: `python -m hive run`

A 4 GB graphics card (such as a GTX 1650) runs 8B models slowly and partly on the CPU. Use `--limit 5` for short runs, or try a smaller model like `llama3.2:3b` and set it in `hive.config.json` under `ollama.model`.

### Claude through the API

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
python -m hive run --backend anthropic --limit 10
```

To keep the key across sessions: `setx ANTHROPIC_API_KEY "sk-ant-..."` and open a new PowerShell window. API calls cost money; check usage in the Anthropic Console.

## 4. Run it every morning

Open **Task Scheduler → Create Basic Task**:

- Trigger: Daily, 08:00
- Action: Start a program
  - Program: `python`
  - Arguments: `-m hive run`
  - Start in: `C:\alyos-hive`

Then check `python -m hive queue` when you sit down.
