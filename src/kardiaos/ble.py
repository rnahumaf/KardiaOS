"""Aquisição local M2. Dados e identificadores permanecem apenas em memória.

Referência de interoperabilidade: ShaneBreazeale/kardia-rs, docs/re/kardia-6l.md
e scripts/bleak_probe.py. Não usa o SDK oficial da AliveCor.
"""
import asyncio
from collections import deque
import hashlib
import queue
import struct
import threading
import time

SERVICE = "ac060001-328c-a28f-9846-5a8aa212661b"
COMMAND = "ac060002-328c-a28f-9846-5a8aa212661b"
ECG = "ac060003-328c-a28f-9846-5a8aa212661b"
FS = 300


def decode_m2(payload):
    if len(payload) != 36:
        raise ValueError("Formato M2 incompatível: eram esperados 36 bytes.")
    return tuple(struct.iter_unpack("<hh", payload))


class MovingAverage:
    def __init__(self, size=5):
        if size < 1:
            raise ValueError("A janela deve ser positiva.")
        self.values = deque(maxlen=size)

    def push(self, value):
        self.values.append(value)
        return sum(self.values) / len(self.values)


class Stream:
    def __init__(self):
        self.events = queue.Queue(maxsize=512)
        self.stop_event = threading.Event()
        self.thread = None
        self.stage = ""
        self.overflow = False

    def emit(self, kind, data):
        try:
            self.events.put_nowait((kind, data))
        except queue.Full:
            self.overflow = True
            self.stop_event.set()

    def status(self, text):
        self.stage = text
        self.emit("status", text)

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def run(self):
        try:
            asyncio.run(self.supervise())
        except Exception as exc:
            self.emit("error", f"{self.stage}: {type(exc).__name__}. Feche o app no celular, confira o pareamento do Windows e tente novamente.")
        finally:
            self.emit("done", None)

    async def supervise(self):
        task = asyncio.create_task(self.acquire())
        try:
            while not task.done() and not self.stop_event.is_set():
                await asyncio.sleep(0.1)
            if not task.done():
                task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def acquire(self):
        from bleak import BleakClient, BleakScanner

        self.status("Procurando o 6L. Toque os dois eletrodos superiores.")
        found = {}
        def advertised(device, adv):
            names = (adv.local_name or "", device.name or "")
            if SERVICE in [u.lower() for u in adv.service_uuids] or any(
                term in name.lower() for name in names for term in ("kardia", "alivecor", "triangle")
            ):
                found[device.address] = (device, adv.local_name or device.name)

        async with BleakScanner(detection_callback=advertised):
            deadline = time.monotonic() + 30
            first_seen = None
            while time.monotonic() < deadline:
                if found and first_seen is None:
                    first_seen = time.monotonic()
                if first_seen and time.monotonic() - first_seen >= 1:
                    break
                await asyncio.sleep(0.1)
        if not found:
            self.emit("error", "6L não encontrado. Feche o app no celular e toque os eletrodos antes de iniciar.")
            return
        if len(found) != 1:
            self.emit("error", "Mais de um candidato encontrado. Deixe apenas o seu 6L ativo e tente novamente.")
            return
        device, name = next(iter(found.values()))
        if not name:
            self.emit("error", "O aparelho não informou o nome necessário para iniciar o modo M2.")
            return

        self.status("Conectando e pareando. Confira se o Windows pede confirmação.")
        disconnected = asyncio.Event()
        async with BleakClient(device, pair=True, timeout=45,
                               disconnected_callback=lambda _: disconnected.set()) as client:
            if client.services.get_service(SERVICE) is None or any(
                client.services.get_characteristic(u) is None for u in (COMMAND, ECG)
            ):
                self.emit("error", "O dispositivo não expõe o serviço ECG esperado do 6L.")
                return
            self.status("Ativando a transmissão M2.")
            ack = asyncio.Event()
            response = []
            def command_received(_, data):
                response.append(bytes(data))
                ack.set()
            await asyncio.wait_for(client.start_notify(COMMAND, command_received), 15)
            token = hashlib.sha256(("Triangle" + name).encode()).hexdigest()[:16]
            await asyncio.wait_for(client.write_gatt_char(COMMAND, f"M2 K{token}".encode(), response=True), 15)
            await asyncio.wait_for(ack.wait(), 8)
            if response[0] != b"\x01":
                self.emit("error", "Resposta de início M2 não reconhecida. Nenhum dado será interpretado como ECG.")
                return
            started = time.monotonic()
            last = [started]
            count = [0]
            fault = [False]
            def received(_, payload):
                if fault[0]:
                    return
                try:
                    samples = decode_m2(payload)
                except ValueError:
                    fault[0] = True
                    self.emit("error", "Pacote incompatível com M2. Aquisição interrompida sem interpretar o conteúdo.")
                    return
                now = time.monotonic()
                self.emit("samples", (now, samples))
                last[0] = now
                count[0] += 1

            await asyncio.wait_for(client.start_notify(ECG, received), 15)
            self.status("Conectado. Aguardando amostras de ECG.")
            last_report = started
            while not disconnected.is_set() and not fault[0]:
                await asyncio.sleep(0.1)
                now = time.monotonic()
                if now - last[0] > 10:
                    self.emit("error", "Sem amostras por 10 segundos. Aquisição encerrada; confira o contato e reinicie.")
                    break
                if now - last_report >= 1:
                    self.emit("stats", (count[0], now - started, now - last[0]))
                    last_report = now
            if disconnected.is_set():
                self.emit("error", "O aparelho desconectou. Os últimos traçados permanecem na tela.")

