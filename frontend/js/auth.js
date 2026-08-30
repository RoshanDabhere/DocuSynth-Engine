import { apiRequest, clearToken, getToken, saveToken } from "./api.js";

const loginForm = document.querySelector("#login-form");
const registerForm = document.querySelector("#register-form");
const message = document.querySelector("#form-message");

function showMessage(text, type = "error") {
  if (!message) return;
  message.textContent = text;
  message.className = `form-message ${type}`;
}

function setSubmitting(form, submitting) {
  const button = form.querySelector("button[type='submit']");
  button.disabled = submitting;
  button.textContent = submitting ? "Please wait…" : button.dataset.label;
}

if (loginForm) {
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setSubmitting(loginForm, true);
    try {
      const values = new FormData(loginForm);
      const result = await apiRequest("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email: values.get("email"), password: values.get("password") }),
      });
      saveToken(result.access_token);
      window.location.replace("dashboard.html");
    } catch (error) {
      showMessage(error.message);
      setSubmitting(loginForm, false);
    }
  });
}

if (registerForm) {
  registerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setSubmitting(registerForm, true);
    try {
      const values = new FormData(registerForm);
      await apiRequest("/auth/register", {
        method: "POST",
        body: JSON.stringify({
          name: values.get("name"),
          email: values.get("email"),
          password: values.get("password"),
        }),
      });
      window.location.replace("login.html?registered=1");
    } catch (error) {
      showMessage(error.message);
      setSubmitting(registerForm, false);
    }
  });
}

document.querySelectorAll("[data-logout]").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    clearToken();
    window.location.replace("login.html");
  });
});

async function protectPage() {
  if (document.body.dataset.protected !== "true") return;
  if (!getToken()) return window.location.replace("login.html");
  try {
    const user = await apiRequest("/auth/me");
    const userName = document.querySelector("[data-user-name]");
    if (userName) userName.textContent = user.name;
  } catch {
    clearToken();
    window.location.replace("login.html");
  }
}

if (new URLSearchParams(window.location.search).has("registered")) {
  showMessage("Account created. You can now sign in.", "success");
}

protectPage();
