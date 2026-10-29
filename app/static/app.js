// Piccoli aiuti dell'interfaccia (niente librerie esterne).
document.addEventListener("click", (e) => {
  const conferma = e.target.closest("[data-conferma]");
  if (conferma && !window.confirm(conferma.dataset.conferma)) {
    e.preventDefault();
    return;
  }
  const spunta = e.target.closest("[data-spunta]");
  if (spunta) {
    const chi = spunta.dataset.spunta;
    document.querySelectorAll("input[name=clienti]").forEach((cb) => {
      if (chi === "tutti") cb.checked = true;
      else if (chi === "nessuno") cb.checked = false;
      else if (cb.dataset.ref === chi) cb.checked = true;
    });
  }
});

document.addEventListener("change", (e) => {
  if (e.target.matches("[data-seleziona-tutto]")) {
    document.querySelectorAll("input[name=sel]").forEach((cb) => (cb.checked = e.target.checked));
  }
  // Scegliendo il cliente, propone il suo referente
  if (e.target.matches("[data-referente-auto]")) {
    const opt = e.target.selectedOptions[0];
    const ref = document.querySelector("select[name=referente_id]");
    if (opt && ref && opt.dataset.referente) ref.value = opt.dataset.referente;
  }
});
