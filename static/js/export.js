/* Roadmap export — captures the on-screen roadmap (header + current gantt
 * configuration) and downloads it as a PNG or single-page PDF. Relies on
 * html2canvas and jsPDF (loaded from CDN before this file). */

function triggerDownload(url, filename) {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function roadmapFilename() {
  const name = (document.querySelector('.roadmap-header__name')?.textContent || 'roadmap').trim();
  return name.replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase() || 'roadmap';
}

async function exportRoadmap(format) {
  const root = document.getElementById('roadmap-export');
  if (!root) { alert('Nothing to export.'); return; }

  document.body.classList.add('exporting');
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));

  try {
    const width = root.scrollWidth;
    const height = root.scrollHeight;
    const canvas = await html2canvas(root, {
      backgroundColor: '#ffffff', scale: 2, useCORS: true,
      width, height, windowWidth: width, windowHeight: height, scrollX: 0, scrollY: 0,
    });
    const base = roadmapFilename();

    if (format === 'png') {
      await new Promise((resolve) => {
        canvas.toBlob((blob) => { triggerDownload(URL.createObjectURL(blob), base + '.png'); resolve(); }, 'image/png');
      });
    } else {
      const imgData = canvas.toDataURL('image/jpeg', 0.95);
      const pxToPt = 0.75;
      const wPt = (canvas.width / 2) * pxToPt;
      const hPt = (canvas.height / 2) * pxToPt;
      const orientation = wPt >= hPt ? 'landscape' : 'portrait';
      const { jsPDF } = window.jspdf;
      const pdf = new jsPDF({ orientation, unit: 'pt', format: [wPt, hPt] });
      pdf.addImage(imgData, 'JPEG', 0, 0, wPt, hPt);
      pdf.save(base + '.pdf');
    }
  } catch (error) {
    console.error('Export failed:', error);
    alert('Export failed: ' + error.message);
  } finally {
    document.body.classList.remove('exporting');
  }
}
