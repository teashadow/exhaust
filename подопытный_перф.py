#!/usr/bin/env python3
"""Синтетические эндпоинты для проверки exhaust. 🔴 OPSEC: localhost, не реальные цели.

  устойчивый — на asyncio (один event loop держит конкурентность БЕЗ потоковой просадки),
               отвечает мгновенно, ловушки обрывает сам. exhaust обязан дать ПРОШЁЛ.
  деградирующий — тоже asyncio, но latency РАСТЁТ с числом одновременно активных запросов, а на
                  ловушке зависает дольше таймаута. exhaust обязан дать ПРОВАЛ.

🔴 Почему asyncio, а не threading: под 20 параллельными Python-потоки честно деградируют из-за
GIL — то есть ThreadingHTTPServer не может быть эталоном «держит нагрузку». Это сам вывод аудита
exhaust (нагрузка → asyncio/Go). Event loop держит сотни соединений в одном потоке ровно.

Сырой HTTP через asyncio.start_server (без сторонних зависимостей).
Запуск: python3 подопытный_перф.py устойчивый 8799  |  деградирующий 8798
"""
import asyncio
import json
import sys

_активных = 0


def _тело_ответа(reply: str) -> bytes:
    полезное = json.dumps({"reply": reply}).encode()
    head = (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Content-Length: " + str(len(полезное)).encode() + b"\r\nConnection: close\r\n\r\n")
    return head + полезное


async def _прочитать_запрос(reader: asyncio.StreamReader) -> str:
    """Минимальный разбор HTTP POST: дочитать заголовки, взять тело по Content-Length."""
    данные = b""
    while b"\r\n\r\n" not in данные:
        кусок = await reader.read(4096)
        if not кусок:
            break
        данные += кусок
    head, _, tail = данные.partition(b"\r\n\r\n")
    длина = 0
    for строка in head.split(b"\r\n"):
        if строка.lower().startswith(b"content-length:"):
            длина = int(строка.split(b":", 1)[1])
    while len(tail) < длина:
        кусок = await reader.read(4096)
        if not кусок:
            break
        tail += кусок
    try:
        return json.loads(tail or b"{}").get("message", "")
    except Exception:
        return ""


def сделать_обработчик(режим: str):
    async def обработать(reader, writer):
        global _активных
        msg = await _прочитать_запрос(reader)
        ловушка = any(w in msg for w in ("infinity", "forever", "indefinitely",
                                         "answer this", "Summarize everything"))
        _активных += 1
        текущих = _активных
        try:
            if режим == "устойчивый":
                await asyncio.sleep(0.002)                 # мгновенно, ловушку обрывает
                reply = "too long — aborted" if ловушка else "ok"
            else:
                if ловушка:
                    await asyncio.sleep(60)                # зависает дольше таймаута
                    reply = "..."
                else:
                    await asyncio.sleep(0.02 * текущих)    # растёт с конкурентностью
                    reply = "ok"
            writer.write(_тело_ответа(reply))
            await writer.drain()
        finally:
            _активных -= 1
            writer.close()

    return обработать


async def main(режим: str, порт: int):
    сервер = await asyncio.start_server(сделать_обработчик(режим), "127.0.0.1", порт)
    async with сервер:
        await сервер.serve_forever()


if __name__ == "__main__":
    режим = sys.argv[1] if len(sys.argv) > 1 else "устойчивый"
    порт = int(sys.argv[2]) if len(sys.argv) > 2 else 8799
    asyncio.run(main(режим, порт))
