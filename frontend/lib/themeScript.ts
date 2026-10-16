// Inline, pre-paint: apply the saved theme before React hydrates (no flash).
export const THEME_KEY = "rs_theme";
export const THEME_SCRIPT = `try{var t=localStorage.getItem("${THEME_KEY}");if(t&&t!=="system")document.documentElement.setAttribute("data-theme",t)}catch(e){}`;
