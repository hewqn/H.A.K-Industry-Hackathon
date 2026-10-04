const TOKEN_KEY = "hak-token";
const ROLE_KEY = "hak-role";

export interface LoginResult {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: { user_id: string; username: string; role: "admin" | "viewer"; created_at: string };
}

export function authToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function isLoggedIn(): boolean {
  return Boolean(authToken());
}

export function isAdmin(): boolean {
  return Boolean(authToken()) && sessionStorage.getItem(ROLE_KEY) === "admin";
}

export function rememberSession(result: LoginResult): void {
  sessionStorage.setItem(TOKEN_KEY, result.access_token);
  sessionStorage.setItem(ROLE_KEY, result.user.role);
}

export function logout(): void {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(ROLE_KEY);
}

export async function restoreSession(): Promise<{ signedIn: boolean; admin: boolean }> {
  const token = authToken();
  if (!token) return { signedIn: false, admin: false };
  const response = await fetch("/api/v1/auth/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    logout();
    return { signedIn: false, admin: false };
  }
  const user = (await response.json()) as LoginResult["user"];
  sessionStorage.setItem(ROLE_KEY, user.role);
  return { signedIn: true, admin: user.role === "admin" };
}

export async function login(username: string, password: string): Promise<LoginResult> {
  const response = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const body = await response.json().catch(() => ({ message: "Login failed." }));
  if (!response.ok) {
    throw new Error(body.message || "Incorrect username or password.");
  }
  rememberSession(body as LoginResult);
  return body as LoginResult;
}

export async function register(username: string, password: string): Promise<LoginResult> {
  const response = await fetch("/api/v1/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const body = await response.json().catch(() => ({ message: "Sign up failed." }));
  if (!response.ok) {
    throw new Error(body.message || "Could not create that account.");
  }
  rememberSession(body as LoginResult);
  return body as LoginResult;
}
