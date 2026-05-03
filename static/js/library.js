document.addEventListener("DOMContentLoaded", () => {
  const select = document.getElementById("libraryPdfSelect");
  const title = document.getElementById("libraryPdfTitle");
  const openBtn = document.getElementById("libraryPdfOpen");

  const canvas = document.getElementById("pdfCanvas");
  const ctx = canvas.getContext("2d");

  const normalPdfView = document.getElementById("normalPdfView");
  const bookPdfView = document.getElementById("bookPdfView");
  let pdfBook = document.getElementById("pdfBook");

  const prevBtn = document.getElementById("pdfPrev");
  const nextBtn = document.getElementById("pdfNext");
  const zoomInBtn = document.getElementById("pdfZoomIn");
  const zoomOutBtn = document.getElementById("pdfZoomOut");
  const bookModeBtn = document.getElementById("pdfBookMode");

  const pageNumEl = document.getElementById("pdfPageNum");
  const pageCountEl = document.getElementById("pdfPageCount");
  const zoomLabel = document.getElementById("pdfZoomLabel");
  const loading = document.getElementById("pdfLoading");

  if (!select || !canvas || !window.pdfjsLib) return;

  pdfjsLib.GlobalWorkerOptions.workerSrc =
    "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

  let pdfDoc = null;
  let pageNum = 1;
  let pageRendering = false;
  let pageNumPending = null;
  let scale = 1.25;

  let bookMode = false;
  let pageFlip = null;

  let pdfLoadToken = 0;
  let bookRenderToken = 0;

  function showLoading(show) {
    if (loading) loading.classList.toggle("hidden", !show);
  }

  function updateZoomLabel() {
    zoomLabel.textContent = `${Math.round(scale * 80)}%`;
  }

  function waitFrame() {
    return new Promise((resolve) => requestAnimationFrame(resolve));
  }

  function recreateBookContainer() {
    bookRenderToken++;

    if (pageFlip) {
      try {
        pageFlip.destroy();
      } catch (error) {
        console.warn("PageFlip destroy warning:", error);
      }
      pageFlip = null;
    }

    const newBook = document.createElement("div");
    newBook.id = "pdfBook";
    newBook.className = "shadow-xl bg-white";

    const oldWrapper = bookPdfView.querySelector('.stf__wrapper');
    const oldBook = bookPdfView.querySelector('#pdfBook');

    if (oldWrapper) oldWrapper.remove();
    if (oldBook) oldBook.remove();
    bookPdfView.appendChild(newBook);

    pdfBook = newBook;
  }

  function renderPage(num) {
    if (!pdfDoc) return;

    const currentPdfToken = pdfLoadToken;

    pageRendering = true;
    showLoading(true);

    pdfDoc.getPage(num)
      .then((page) => {
        if (currentPdfToken !== pdfLoadToken) return null;

        const viewport = page.getViewport({ scale });

        canvas.height = viewport.height;
        canvas.width = viewport.width;

        return page.render({
          canvasContext: ctx,
          viewport: viewport,
        }).promise;
      })
      .then(() => {
        if (currentPdfToken !== pdfLoadToken) return;

        pageRendering = false;
        showLoading(false);
        pageNumEl.textContent = num;

        if (pageNumPending !== null) {
          const pending = pageNumPending;
          pageNumPending = null;
          renderPage(pending);
        }
      })
      .catch((error) => {
        if (currentPdfToken !== pdfLoadToken) return;

        console.error("PDF page render error:", error);
        pageRendering = false;
        showLoading(false);
      });
  }

  function queueRenderPage(num) {
    if (pageRendering) {
      pageNumPending = num;
    } else {
      renderPage(num);
    }
  }

  async function renderBook() {
    if (!pdfDoc || !window.St) return;

    const currentPdfToken = pdfLoadToken;

    recreateBookContainer();
    const currentBookToken = bookRenderToken;

    showLoading(true);

    await waitFrame();

    const totalPages = pdfDoc.numPages;
    const maxPages = Math.min(totalPages, 100);
    const pages = [];

    for (let i = 1; i <= maxPages; i++) {
      if (
        currentPdfToken !== pdfLoadToken ||
        currentBookToken !== bookRenderToken ||
        !bookMode
      ) {
        showLoading(false);
        return;
      }

      try {
        const page = await pdfDoc.getPage(i);

        if (
          currentPdfToken !== pdfLoadToken ||
          currentBookToken !== bookRenderToken ||
          !bookMode
        ) {
          showLoading(false);
          return;
        }

        const viewport = page.getViewport({ scale: 1.15 });

        const tempCanvas = document.createElement("canvas");
        const tempCtx = tempCanvas.getContext("2d");

        tempCanvas.width = viewport.width;
        tempCanvas.height = viewport.height;

        await page.render({
          canvasContext: tempCtx,
          viewport: viewport,
        }).promise;

        if (
          currentPdfToken !== pdfLoadToken ||
          currentBookToken !== bookRenderToken ||
          !bookMode
        ) {
          showLoading(false);
          return;
        }

        const img = document.createElement("img");
        img.src = tempCanvas.toDataURL("image/jpeg", 0.92);
        img.className = "w-full h-full object-contain bg-white";
        img.draggable = false;

        const pageDiv = document.createElement("div");
        pageDiv.className = "bg-white overflow-hidden flex items-center justify-center";
        pageDiv.appendChild(img);

        pages.push(pageDiv);
      } catch (error) {
        console.warn(`No se pudo renderizar la página ${i}:`, error);
      }
    }

    if (
      currentPdfToken !== pdfLoadToken ||
      currentBookToken !== bookRenderToken ||
      !bookMode ||
      !pages.length
    ) {
      showLoading(false);
      return;
    }

    pdfBook.innerHTML = "";
    pages.forEach((page) => pdfBook.appendChild(page));

    await waitFrame();

    try {
      pageFlip = new St.PageFlip(pdfBook, {
        width: 430,
        height: 620,
        size: "fixed",
        maxShadowOpacity: 0.3,
        showCover: true,
        mobileScrollSupport: false,
        useMouseEvents: true,
        flippingTime: 750,
        drawShadow: true,
      });

      pageFlip.loadFromHTML(pages);

      pageFlip.on("flip", (e) => {
        pageNum = e.data + 1;
        pageNumEl.textContent = pageNum;
      });
    } catch (error) {
      console.error("PageFlip init error:", error);
    }

    showLoading(false);
  }

  function enterNormalMode() {
    bookMode = false;

    recreateBookContainer();

    bookPdfView.classList.add("hidden");
    normalPdfView.classList.remove("hidden");
    bookModeBtn.textContent = "Modo libro";
  }

  function enterBookMode() {
    bookMode = true;

    normalPdfView.classList.add("hidden");
    bookPdfView.classList.remove("hidden");
    bookModeBtn.textContent = "Vista normal";

    renderBook();
  }

  function toggleBookMode() {
    if (bookMode) {
      enterNormalMode();
      renderPage(pageNum);
    } else {
      enterBookMode();
    }
  }

  function loadPdf(url) {
    pdfLoadToken++;
    bookRenderToken++;

    pageNum = 1;
    pageNumPending = null;
    pageRendering = false;

    showLoading(true);

    const currentPdfToken = pdfLoadToken;

    pdfjsLib.getDocument(url).promise
      .then((pdf) => {
        if (currentPdfToken !== pdfLoadToken) return;

        pdfDoc = pdf;

        pageCountEl.textContent = pdf.numPages;
        pageNumEl.textContent = pageNum;

        if (bookMode) {
          renderBook();
        } else {
          renderPage(pageNum);
        }
      })
      .catch((error) => {
        if (currentPdfToken !== pdfLoadToken) return;

        console.error("PDF loading error:", error);
        showLoading(false);
        alert("No se pudo cargar el PDF seleccionado.");
      });
  }

  prevBtn.addEventListener("click", () => {
    if (!pdfDoc || pageNum <= 1) return;

    if (bookMode && pageFlip) {
      pageFlip.flipPrev();
    } else {
      pageNum--;
      queueRenderPage(pageNum);
    }
  });

  nextBtn.addEventListener("click", () => {
    if (!pdfDoc || pageNum >= pdfDoc.numPages) return;

    if (bookMode && pageFlip) {
      pageFlip.flipNext();
    } else {
      pageNum++;
      queueRenderPage(pageNum);
    }
  });

  zoomInBtn.addEventListener("click", () => {
    if (!pdfDoc || scale >= 2.5) return;

    scale += 0.15;
    updateZoomLabel();

    if (bookMode) {
      renderBook();
    } else {
      queueRenderPage(pageNum);
    }
  });

  zoomOutBtn.addEventListener("click", () => {
    if (!pdfDoc || scale <= 0.7) return;

    scale -= 0.15;
    updateZoomLabel();

    if (bookMode) {
      renderBook();
    } else {
      queueRenderPage(pageNum);
    }
  });

  bookModeBtn.addEventListener("click", toggleBookMode);

  select.addEventListener("change", () => {
    const selectedOption = select.options[select.selectedIndex];
    const pdfUrl = select.value;
    const pdfTitle = selectedOption.textContent.trim();

    title.textContent = pdfTitle;
    openBtn.href = pdfUrl;

    enterNormalMode();
    loadPdf(pdfUrl);
  });

  updateZoomLabel();
  loadPdf(select.value);
});
