# GuiaClick

Generador de **guías paso a paso** para **Windows** (estilo Scribe, pero **100% local**): graba tus clics y GuiaClick captura cada pantalla, la anota y monta la guía lista para compartir.

## Funciones

- **Grabación de pasos**: cada clic (izquierdo y, opcionalmente, derecho) captura la pantalla del monitor correspondiente con el punto resaltado y numerado.
- **Editor**: reordena, duplica o borra pasos; edita título y nota de cada uno; vista previa en vivo.
- **Privacidad**: difumina zonas sensibles arrastrando sobre la imagen.
- **Textos con IA** (opcional, [Ollama](https://ollama.com)): reescribe los pasos de forma clara e imperativa; sin Ollama, títulos automáticos a partir de la ventana activa.
- **Exportación**: HTML autocontenido (imágenes embebidas), Markdown (con carpeta de imágenes) y **PDF** (portada + un paso por página).

## Stack

Python 3 + Tkinter (ttk) · mss + Pillow · PyMuPDF (export PDF) · ctypes/Win32 · Ollama opcional.

Depende del paquete compartido de la suite [`octonove-core`](https://github.com/Octonove/octonove-core) (tema, capa Ollama, config): debe estar en el `sys.path` del entorno (vía `.pth` o copia junto al proyecto).

## Compilar

```powershell
.\build\build.ps1              # ejecutable (PyInstaller onedir)
.\build\build-installer.ps1    # instalador (Inno Setup)
```

## Tests

```powershell
python -m pytest tests/ -q
```

## Licencia

[MIT](LICENSE) — © 2026 Octonove.
