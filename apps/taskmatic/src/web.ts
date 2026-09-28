import { createServer, type Server } from "node:http";
import { isIPv4 } from "node:net";
import { renderPage } from "./export.js";
import { Store } from "./store.js";

export async function serve(
  root: string | undefined,
  host = "127.0.0.1",
  port = 8765,
): Promise<Server> {
  if (host === "localhost") host = "127.0.0.1";
  if (!isIPv4(host) || host.split(".")[0] !== "127")
    throw new Error("host must be an IPv4 loopback address");
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error("invalid port");
  const check = await Store.open(root, true);
  check.close();
  const server = createServer((request, response) => {
    void (async () => {
      response.setHeader("Cache-Control", "no-store");
      response.setHeader("X-Content-Type-Options", "nosniff");
      if (request.method !== "GET") {
        response.writeHead(405);
        response.end("read-only board\n");
        return;
      }
      const path = (request.url ?? "/").split("?")[0];
      if (!["/", "/snapshot.json"].includes(path)) {
        response.writeHead(404);
        response.end("not found\n");
        return;
      }
      const store = await Store.open(root, true);
      let snapshot;
      try {
        snapshot = store.snapshot();
      } finally {
        store.close();
      }
      const body =
        path === "/" ? await renderPage(snapshot) : `${JSON.stringify(snapshot, null, 2)}\n`;
      response.writeHead(200, {
        "Content-Type": path === "/" ? "text/html; charset=utf-8" : "application/json",
        "Content-Length": Buffer.byteLength(body),
      });
      response.end(body);
    })().catch(() => {
      response.writeHead(503);
      response.end("taskmatic store unavailable\n");
    });
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, host, resolve);
  });
  return server;
}
