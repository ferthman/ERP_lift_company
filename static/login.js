// Visiting the sign-in screen ends offline access to the last local identity.
localStorage.removeItem('liftcrm-mobile-identity');
const passwordInput = document.getElementById('password');
document.getElementById('show-password').addEventListener('click', (event) => {
  const visible = passwordInput.type === 'password';
  passwordInput.type = visible ? 'text' : 'password';
  event.currentTarget.textContent = visible ? 'Скрыть' : 'Показать';
  event.currentTarget.setAttribute('aria-label', visible ? 'Скрыть пароль' : 'Показать пароль');
  event.currentTarget.setAttribute('aria-pressed', String(visible));
});
passwordInput.addEventListener('keyup', (event) => document.getElementById('caps-warning').classList.toggle('hidden', !event.getModifierState('CapsLock')));
document.getElementById('login-form').addEventListener('submit', (event) => {
  const button = event.currentTarget.querySelector('[type=submit]');
  button.disabled = true; button.textContent = 'Входим…';
});
