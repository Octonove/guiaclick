# GuiaClick

Generador de **guías paso a paso** para **Windows** (estilo Scribe, pero **100% local**): graba tus clics y GuiaClick captura cada pantalla, la anota y monta la guía lista para compartir.

## ⬇️ Descargar (Windows 10/11)

### ➡️ [**Descargar GuiaClick (instalador .exe)**](https://github.com/Octonove/guiaclick/releases/latest/download/GuiaClick-Setup.exe)

Descarga **directa** del instalador, sin registro. También puedes ver la [última versión y notas](https://github.com/Octonove/guiaclick/releases/latest).

> Si Windows muestra *"Windows protegió tu PC"* (es normal en programas nuevos sin firma): pulsa **Más información → Ejecutar de todas formas**. Se instala sin permisos de administrador.

---

## Funciones

- **Grabación de pasos**: cada clic (izquierdo y, opcionalmente, derecho) captura la pantalla del monitor correspondiente con el punto resaltado y numerado. Los dobles clics se fusionan en un solo paso, y la barra de grabación **no aparece en las capturas** (Windows 10/11) y puedes arrastrarla a donde no moleste.
- **Editor**: reordena, duplica o borra pasos; edita título y nota de cada uno; vista previa en vivo.
- **Difuminar y recortar**: oculta zonas sensibles arrastrando sobre la imagen, o **recorta** el área del clic para resaltar solo lo importante de ese paso (con *deshacer recorte*).
- **Guardar y continuar después**: guarda la guía como proyecto `.guiaclick` y retómala en otra sesión. Si cierras sin guardar, al volver a abrir te ofrece **recuperar** la guía autoguardada.
- **Continuar una guía**: al grabar sobre una guía abierta puedes **añadir** los nuevos pasos al final (o empezar de cero). También puedes **reemplazar la imagen** de un paso concreto por otra captura.
- **Textos con IA** (opcional, [Ollama](https://ollama.com) o una API de OpenAI/Gemini/Anthropic): reescribe los pasos de forma clara e imperativa; sin IA, títulos automáticos a partir de la ventana activa.
- **Exportación**: HTML autocontenido (imágenes embebidas), Markdown (con carpeta de imágenes) y **PDF** con **maquetado fluido** (varios pasos por página, sin huecos en blanco) y el **título de cada paso** bien visible.

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
