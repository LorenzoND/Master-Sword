# Master-Sword

App nativo de Windows (sem browser) pra controlar e monitorar CPU + GPU em notebook com gargalo
térmico. Substitui o combo `nvidia-smi -lgc` + ThrottleStop + overlay do MSI Afterburner por uma
coisa só, leve, que fica na bandeja.

Feito pro MSI GS66 Stealth 10SE (i7-10750H + RTX 2060). O núcleo (NVML + Power Plan) serve pra
qualquer notebook Intel + NVIDIA; o controle de fan é específico de notebooks MSI com EC compatível.

## O que faz

- **Painel**: temperatura, clock, power e uso de GPU/CPU, fans, RAM/VRAM e FPS, com cor por nível.
  Gráfico com escala fixa (1, 5 ou 15 min), faixa de alerta, linha onde a GPU começa a segurar o
  clock e faixas marcando quando GPU/CPU foram limitadas.
- **Motivo de limite**: diz se a GPU está sendo segurada por temperatura ou power (NVML) e se a CPU
  está em throttle térmico ou de power (MSR, só leitura).
- **Controles**: lock de clock da GPU (= `nvidia-smi -lgc`), modo de boost da CPU (todos os 7 do
  Windows, não só liga/desliga).
- **Perfis**: aplicam GPU + boost + fan de uma vez; cada item pode ficar em "não mexer". Editar,
  duplicar, excluir, capturar o estado real, perfil ao iniciar e troca rápida pela bandeja.
- **Overlay**: dentro do jogo via RTSS (transparente, não pega clique, funciona em tela cheia, com
  FPS/frametime e gráfico de frametime) ou janela de desktop. Liga/desliga por atalho global.
- **Alertas**: notificação do Windows e overlay em vermelho acima do limite configurado.
- **Fan (EC)**: leitura de % (e RPM quando disponível), modo do fan, Cooler Boost e modo MSI
  (Eco/Comfort/Sport/Turbo). Escrita só com firmware reconhecido, depois de habilitar, e cada
  escrita é conferida lendo de volta. Curva de fan experimental.
- **Processos**: o que mais consome CPU/RAM/VRAM; baixar prioridade ou encerrar (com confirmação).

## Instalar

Requer Windows, Python 3.12+, GPU NVIDIA, CPU Intel e o driver [PawnIO](https://github.com/namazso/PawnIO)
(`winget install PawnIO`) pra sensores de CPU, MSR e EC.

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File install.ps1
```

O `install.ps1` pede UAC uma vez e cria:
- a tarefa agendada **Master-Sword** ("executar com privilégios mais altos"), que sobe o
  `pythonw.exe` já elevado — sem janela de console e sem UAC a cada abertura;
- o atalho **Master-Sword** na área de trabalho, que roda o `pythonw` sem elevação e só dispara a
  tarefa. (Elevar o `python.exe` do venv direto é barrado pelo SmartScreen.)

Clicar no atalho com o app aberto só traz a janela pra frente. O X da janela esconde na bandeja;
sair é pelo menu da bandeja. "Iniciar com o Windows" fica em Ajustes.

## Estrutura

```
main.pyw              entrada (sem console): lança via tarefa, instância única, sobe tudo
install.ps1           tarefa agendada + atalho
core/
  gpu.py              NVML: leitura, motivo de limite, lock de clock, reconexão automática
  cpu.py              boost (powercfg), sensores (LibreHardwareMonitor), limite via MSR
  ec.py               EC do MSI via PawnIO: fans, Cooler Boost, modos, curva
  sampler.py          thread de coleta 1 Hz + histórico de 15 min
  controller.py       toda ação que muda hardware passa por aqui (UI, bandeja, perfis)
  profiles.py         perfis v2 (converte os da v1)
  state.py            o que foi aplicado (o lock da GPU sobrevive ao app fechar)
  settings.py         preferências
  rtss.py / osd.py    overlay in-game via memória compartilhada do RTSS
  overlay.py          escolhe RTSS / desktop a cada leitura
  alerts.py, hotkey.py, launcher.py, logsetup.py, scan.py
ui/
  app.py              janela, barra lateral, loop, bandeja
  pages/              painel, perfis, fan, overlay, processos, ajustes
  theme.py, widgets.py, tray.py, desktop_overlay.py, icon.py
```

Logs em `logs/` (3 arquivos de 1 MB). Dev: `.venv\Scripts\python main.pyw --no-elevate` roda sem
admin (lock, sensores de CPU e fan ficam desativados).

## Cuidados

- O lock da GPU continua no driver com o app fechado (como o `nvidia-smi`). O app lembra o que
  aplicou e descarta isso quando o PC reinicia. Em Ajustes dá pra soltar o lock ao sair.
- Se o Dragon Center / MSI Center estiver aberto, ele pode trocar o modo do fan e o modo MSI por
  conta própria. O app sempre mostra o valor real lido do EC.
- Escrita no EC é a parte de risco: a curva de fan é experimental e só aceita curva crescente com
  o último ponto ≥ 80%.
