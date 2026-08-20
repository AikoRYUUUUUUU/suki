/**
 * Leitor de .zip mínimo, sem dependência externa - só o necessário pra tirar
 * as imagens de um capítulo de dentro de um zip. Em vez de reimplementar o
 * algoritmo de descompressão (DEFLATE) na mão, usa a DecompressionStream
 * nativa do navegador (formato "deflate-raw", que é exatamente o que uma
 * entrada de .zip usa por dentro, sem cabeçalho zlib/gzip) - só o FORMATO do
 * container .zip (Central Directory + Local File Headers) é lido na mão
 * aqui, que é simples o bastante pra isso valer a pena.
 *
 * Limitações conhecidas (não deve importar pra um .zip de capítulo de mangá):
 * sem suporte a ZIP64 (arquivos gigantes/milhares de entradas), sem suporte
 * a .zip criptografado, só entende os métodos "stored" (sem compressão) e
 * "deflate" (o único método de compressão que ferramentas de zip comuns usam).
 */
async function readZipImages(file) {
  const buf = await file.arrayBuffer();
  const view = new DataView(buf);
  const bytes = new Uint8Array(buf);

  const EOCD_SIG = 0x06054b50;
  const maxCommentSize = 65536;
  const searchStart = Math.max(0, bytes.length - 22 - maxCommentSize);
  let eocdOffset = -1;
  for (let i = bytes.length - 22; i >= searchStart; i--) {
    if (view.getUint32(i, true) === EOCD_SIG) {
      eocdOffset = i;
      break;
    }
  }
  if (eocdOffset === -1) {
    throw new Error("arquivo .zip inválido ou corrompido");
  }

  const entryCount = view.getUint16(eocdOffset + 10, true);
  const centralDirOffset = view.getUint32(eocdOffset + 16, true);

  const CENTRAL_SIG = 0x02014b50;
  const entries = [];
  let offset = centralDirOffset;
  for (let i = 0; i < entryCount; i++) {
    if (view.getUint32(offset, true) !== CENTRAL_SIG) break;
    const method = view.getUint16(offset + 10, true);
    const compressedSize = view.getUint32(offset + 20, true);
    const nameLen = view.getUint16(offset + 28, true);
    const extraLen = view.getUint16(offset + 30, true);
    const commentLen = view.getUint16(offset + 32, true);
    const localHeaderOffset = view.getUint32(offset + 42, true);
    const nameBytes = bytes.subarray(offset + 46, offset + 46 + nameLen);
    const name = new TextDecoder("utf-8").decode(nameBytes);

    entries.push({ name: name, method: method, compressedSize: compressedSize, localHeaderOffset: localHeaderOffset });
    offset += 46 + nameLen + extraLen + commentLen;
  }

  const imageExt = /\.(png|jpe?g|webp)$/i;
  const imageEntries = entries.filter(function (e) {
    return imageExt.test(e.name) && e.name.indexOf("__MACOSX") === -1 && !e.name.endsWith("/");
  });
  imageEntries.sort(function (a, b) {
    return a.name.localeCompare(b.name, undefined, { numeric: true });
  });

  const LOCAL_SIG = 0x04034b50;
  const results = [];
  for (const entry of imageEntries) {
    const lo = entry.localHeaderOffset;
    if (view.getUint32(lo, true) !== LOCAL_SIG) {
      throw new Error(`cabeçalho local inválido em "${entry.name}"`);
    }
    const localNameLen = view.getUint16(lo + 26, true);
    const localExtraLen = view.getUint16(lo + 28, true);
    const dataStart = lo + 30 + localNameLen + localExtraLen;
    const compressed = bytes.subarray(dataStart, dataStart + entry.compressedSize);

    let outBytes;
    if (entry.method === 0) {
      outBytes = compressed;
    } else if (entry.method === 8) {
      const ds = new DecompressionStream("deflate-raw");
      const writer = ds.writable.getWriter();
      writer.write(compressed);
      writer.close();
      outBytes = new Uint8Array(await new Response(ds.readable).arrayBuffer());
    } else {
      throw new Error(`"${entry.name}" usa um método de compressão não suportado`);
    }

    const ext = entry.name.split(".").pop().toLowerCase();
    const mime = ext === "png" ? "image/png" : ext === "webp" ? "image/webp" : "image/jpeg";
    results.push({ name: entry.name, blob: new Blob([outBytes], { type: mime }) });
  }

  return results;
}

window.readZipImages = readZipImages;
