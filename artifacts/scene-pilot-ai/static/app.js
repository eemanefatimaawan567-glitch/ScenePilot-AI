(function () {
  "use strict";

  const fileInput = document.getElementById("screenplay-file");
  const dropzone = document.getElementById("dropzone");
  const dropzoneTitle = document.getElementById("dropzone-title");
  const dropzoneHint = document.getElementById("dropzone-hint");
  const selectedFile = document.getElementById("selected-file");
  const fileName = document.getElementById("file-name");
  const fileSize = document.getElementById("file-size");
  const removeFile = document.getElementById("remove-file");
  const analyzeButton = document.getElementById("analyze-button");
  const formMessage = document.getElementById("form-message");
  const toast = document.getElementById("toast");
  const analysisState = document.querySelector(".analysis-state");
  const analysisTitle = document.getElementById("analysis-title");
  const analysisMeta = document.getElementById("analysis-meta");
  const analysisResults = document.getElementById("analysis-results");
  const agenticWorkflow = document.getElementById("agentic-workflow");
  const productionRecovery = document.getElementById("production-recovery");
  const disruptionInput = document.getElementById("disruption-input");
  const replanButton = document.getElementById("replan-button");
  const recoveryMessage = document.getElementById("recovery-message");
  const recoveryResults = document.getElementById("recovery-results");
  const recoveryDisruptionSummary = document.getElementById("recovery-disruption-summary");
  const recoveryAffectedScenes = document.getElementById("recovery-affected-scenes");
  const recoveryDirectorDecision = document.getElementById("recovery-director-decision");
  const recoverySchedulingRationale = document.getElementById("recovery-scheduling-rationale");
  const recoveryFinalDecision = document.getElementById("recovery-final-decision");
  const sceneList = document.getElementById("scene-list");
  const storySignalSummary = document.getElementById("story-signal-summary");
  const storySignalMetrics = document.getElementById("story-signal-metrics");
  const sceneArchitectureSummary = document.getElementById("scene-architecture-summary");
  const sceneArchitectureMetrics = document.getElementById("scene-architecture-metrics");
  const productionPressureSummary = document.getElementById("production-pressure-summary");
  const productionPressureMetrics = document.getElementById("production-pressure-metrics");
  let activeFile = null;
  let activeAnalysis = null;
  let toastTimer = null;

  function formatBytes(bytes) {
    if (!bytes) return "0 KB";
    if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 3600);
  }

  function setMessage(message) {
    formMessage.textContent = message;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    }[character]));
  }

  function listText(values, fallback = "Not detected") {
    return Array.isArray(values) && values.length ? values.join(", ") : fallback;
  }

  function sceneCountLabel(count) {
    return `${count} scene${count === 1 ? "" : "s"}`;
  }

  function markCardReady(cardIndex, footerLabel) {
    const card = document.querySelectorAll(".analysis-card")[cardIndex];
    if (!card) return;
    const status = card.querySelector(".card-status");
    const footer = card.querySelector(".card-footer span");
    if (status) status.textContent = "ready";
    if (footer) footer.textContent = footerLabel;
  }

  function renderScene(scene) {
    const risks = listText(scene.production_risks, "None detected");
    return `
      <article class="scene-row">
        <div class="scene-row-head">
          <span>Scene ${escapeHtml(String(scene.number).padStart(2, "0"))}</span>
          <span>${escapeHtml(scene.int_ext)} · ${escapeHtml(scene.day_night)}</span>
        </div>
        <h4>${escapeHtml(scene.location)}</h4>
        <div class="scene-fields">
          <div class="scene-field">
            <span class="scene-field-label">Characters</span>
            <span class="scene-field-value">${escapeHtml(listText(scene.characters))}</span>
          </div>
          <div class="scene-field">
            <span class="scene-field-label">Important props</span>
            <span class="scene-field-value">${escapeHtml(listText(scene.important_props))}</span>
          </div>
          <div class="scene-field">
            <span class="scene-field-label">Requirements</span>
            <span class="scene-field-value">${escapeHtml(listText(scene.production_requirements))}</span>
          </div>
          <div class="scene-field">
            <span class="scene-field-label">Production risks</span>
            <span class="scene-field-value is-risk">${escapeHtml(risks)}</span>
          </div>
        </div>
      </article>
    `;
  }

  function renderAgentSection(section, elementId, fields) {
    const card = document.getElementById(elementId);
    if (!card) return;

    card.querySelector(".agent-summary").textContent = section.summary;
    card.querySelector(".agent-points").innerHTML = fields.map(({ key, label }) => `
      <div class="agent-point">
        <span class="agent-point-label">${escapeHtml(label)}</span>
        <span class="agent-point-value">${escapeHtml(listText(section[key]))}</span>
      </div>
    `).join("");
  }

  function renderAgenticWorkflow(analysis) {
    renderAgentSection(analysis.director_agent || {}, "director-agent", [
      { key: "production_priorities", label: "Priorities" },
      { key: "key_decisions", label: "Key decisions" },
    ]);
    renderAgentSection(analysis.continuity_agent || {}, "continuity-agent", [
      { key: "continuity_risks", label: "Continuity risks" },
      { key: "affected_elements", label: "Affected elements" },
      { key: "recommendations", label: "Recommendations" },
    ]);
    renderAgentSection(analysis.production_risk_agent || {}, "production-risk-agent", [
      { key: "risks", label: "Risks" },
      { key: "high_risk_scenes", label: "High-risk scenes" },
      { key: "mitigations", label: "Mitigations" },
    ]);
    renderAgentSection(analysis.scheduling_agent || {}, "scheduling-agent", [
      { key: "shooting_order", label: "Recommended order" },
      { key: "scheduling_rationale", label: "Rationale" },
    ]);
    renderAgentSection(analysis.director_decision || {}, "director-decision", [
      { key: "final_priorities", label: "Final priorities" },
      { key: "approved_shooting_strategy", label: "Shooting strategy" },
      { key: "actions", label: "Next actions" },
    ]);
    agenticWorkflow.hidden = false;
  }

  function renderRecoveryPoints(elementId, label, values) {
    const element = document.getElementById(elementId);
    if (!element) return;
    element.innerHTML = `
      <div class="recovery-point">
        <span class="agent-point-label">${escapeHtml(label)}</span>
        <span class="agent-point-value">${escapeHtml(listText(values))}</span>
      </div>
    `;
  }

  function renderRecovery(recovery) {
    recoveryDisruptionSummary.textContent = recovery.disruption_summary;
    recoveryAffectedScenes.textContent =
      `Affected scenes: ${listText(recovery.affected_scenes, "None specified")}`;

    recoveryDirectorDecision.textContent = recovery.director_agent.decision;
    renderRecoveryPoints(
      "recovery-director-priorities",
      "Priorities",
      recovery.director_agent.priorities,
    );

    renderRecoveryPoints(
      "recovery-continuity-issues",
      "Issues",
      recovery.continuity_agent.issues,
    );
    renderRecoveryPoints(
      "recovery-continuity-recommendations",
      "Recommendations",
      recovery.continuity_agent.recommendations,
    );

    renderRecoveryPoints(
      "recovery-risk-risks",
      "New risks",
      recovery.production_risk_agent.new_risks,
    );
    renderRecoveryPoints(
      "recovery-risk-mitigations",
      "Mitigations",
      recovery.production_risk_agent.mitigations,
    );

    renderRecoveryPoints(
      "recovery-scheduling-order",
      "Revised order",
      recovery.scheduling_agent.revised_shooting_order,
    );
    recoverySchedulingRationale.textContent = recovery.scheduling_agent.rationale;

    recoveryFinalDecision.textContent = recovery.recovery_plan.final_decision;
    renderRecoveryPoints(
      "recovery-actions",
      "Actions",
      recovery.recovery_plan.actions,
    );
    recoveryResults.hidden = false;
  }

  function renderAnalysis(analysis) {
    const locations = [...new Set((analysis.scenes || []).map((scene) => scene.location).filter(Boolean))];
    const intExt = [...new Set((analysis.scenes || []).map((scene) => scene.int_ext).filter(Boolean))];
    const dayNight = [...new Set((analysis.scenes || []).map((scene) => scene.day_night).filter(Boolean))];
    const riskCount = (analysis.production_risks || []).length;

    storySignalSummary.textContent = analysis.logline;
    storySignalMetrics.hidden = false;
    storySignalMetrics.innerHTML = `
      <span><b>Genre</b> ${escapeHtml(analysis.genre)}</span>
      <span><b>Tone</b> ${escapeHtml(analysis.tone)}</span>
    `;

    sceneArchitectureSummary.textContent =
      `${sceneCountLabel(analysis.total_scenes)} across ${locations.length} location${locations.length === 1 ? "" : "s"}.`;
    sceneArchitectureMetrics.hidden = false;
    sceneArchitectureMetrics.innerHTML = `
      <span><b>Setups</b> ${escapeHtml(listText(locations))}</span>
      <span><b>Coverage</b> ${escapeHtml(listText(intExt))} · ${escapeHtml(listText(dayNight))}</span>
    `;

    productionPressureSummary.innerHTML =
      `Estimated complexity: <strong>${escapeHtml(analysis.estimated_complexity)}</strong>. ${riskCount} risk${riskCount === 1 ? "" : "s"} detected.`;
    productionPressureMetrics.hidden = false;
    productionPressureMetrics.innerHTML = `
      <span><b>Risks</b> ${escapeHtml(listText(analysis.production_risks, "None detected"))}</span>
      <span><b>Needs</b> ${escapeHtml(listText(analysis.production_requirements, "None detected"))}</span>
    `;

    markCardReady(0, "Signal captured");
    markCardReady(1, "Scenes mapped");
    markCardReady(2, "Pressure assessed");

    analysisState.innerHTML = '<span class="state-dot"></span>Analysis ready';
    analysisTitle.textContent = analysis.title;
    analysisMeta.textContent = `${sceneCountLabel(analysis.total_scenes)} · ${analysis.estimated_complexity} complexity`;
    sceneList.innerHTML = analysis.scenes.length
      ? analysis.scenes.map(renderScene).join("")
      : '<div class="scene-row"><span class="scene-field-value">No scene headings were detected in this screenplay.</span></div>';
    analysisResults.hidden = false;
    renderAgenticWorkflow(analysis);
    activeAnalysis = analysis;
    disruptionInput.value = "";
    recoveryResults.hidden = true;
    recoveryMessage.textContent = "";
    productionRecovery.hidden = false;
  }

  function isAccepted(file) {
    if (!file) return false;
    const extension = file.name.toLowerCase().split(".").pop();
    return extension === "pdf" || extension === "txt";
  }

  function selectFile(file) {
    if (!isAccepted(file)) {
      setMessage("Please choose a PDF or TXT screenplay.");
      showToast("That file type is not supported. Choose PDF or TXT.");
      return;
    }
    if (file.size > 25 * 1024 * 1024) {
      setMessage("This file is larger than the 25 MB workspace limit.");
      showToast("The screenplay is too large for this workspace.");
      return;
    }

    activeFile = file;
    fileName.textContent = file.name;
    fileSize.textContent = formatBytes(file.size);
    selectedFile.hidden = false;
    dropzoneTitle.textContent = "Screenplay ready for intake";
    dropzoneHint.innerHTML = "Choose another file <u>or drag it here</u>";
    analyzeButton.disabled = false;
    setMessage("");
  }

  function clearFile() {
    activeFile = null;
    fileInput.value = "";
    selectedFile.hidden = true;
    dropzoneTitle.textContent = "Drop your screenplay here";
    dropzoneHint.innerHTML = "or <u>browse from your computer</u>";
    analyzeButton.disabled = true;
    setMessage("");
  }

  fileInput.addEventListener("change", (event) => {
    selectFile(event.target.files[0]);
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.add("is-dragging");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.remove("is-dragging");
    });
  });

  dropzone.addEventListener("drop", (event) => {
    selectFile(event.dataTransfer.files[0]);
  });

  removeFile.addEventListener("click", clearFile);

  analyzeButton.addEventListener("click", async () => {
    if (!activeFile) return;

    if (!activeFile.name.toLowerCase().endsWith(".txt")) {
      setMessage("Screenplay Analysis currently supports TXT files only.");
      showToast("Choose a TXT screenplay to run the first analysis.");
      return;
    }

    analyzeButton.disabled = true;
    analyzeButton.innerHTML = 'Reading screenplay <span class="button-arrow" aria-hidden="true">···</span>';
    setMessage("Reading the screenplay and preparing its production report.");

    try {
      const formData = new FormData();
      formData.append("screenplay", activeFile);
      const response = await fetch("/analyze", {
        method: "POST",
        body: formData,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error || "The screenplay could not be analyzed.");
      }

      renderAnalysis(payload);
      setMessage("Analysis complete. Review the production report below.");
      showToast("Production analysis ready.");
    } catch (error) {
      const message = error instanceof Error
        ? error.message
        : "Gemini is unavailable right now. Please try again.";
      setMessage(message);
      showToast(message);
    } finally {
      analyzeButton.disabled = false;
      analyzeButton.innerHTML = 'Analyze Screenplay <span class="button-arrow" aria-hidden="true">↗</span>';
    }
  });

  replanButton.addEventListener("click", async () => {
    if (!activeAnalysis) return;

    const disruption = disruptionInput.value.trim();
    if (!disruption) {
      recoveryMessage.textContent = "Describe the production disruption first.";
      showToast("Add a disruption before replanning.");
      return;
    }

    replanButton.disabled = true;
    replanButton.innerHTML = 'Replanning <span class="button-arrow" aria-hidden="true">···</span>';
    recoveryMessage.textContent = "Coordinating the recovery plan around the existing analysis.";

    try {
      const response = await fetch("/replan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          analysis: activeAnalysis,
          disruption,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error || "The production recovery plan could not be created.");
      }

      renderRecovery(payload);
      recoveryMessage.textContent = "Recovery plan ready. Review the revised production direction below.";
      showToast("Production recovery plan ready.");
    } catch (error) {
      const message = error instanceof Error
        ? error.message
        : "Gemini is unavailable right now. Please try again.";
      recoveryMessage.textContent = message;
      showToast(message);
    } finally {
      replanButton.disabled = false;
      replanButton.innerHTML = 'Replan Production <span class="button-arrow" aria-hidden="true">↗</span>';
    }
  });

  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("is-active"));
      link.classList.add("is-active");
    });
  });
}());