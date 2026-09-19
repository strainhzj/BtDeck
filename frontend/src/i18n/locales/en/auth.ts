/*
 * Copyright (C) 2025 BTDeck Contributors
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

/** Sign-in and session (auth group, P2 first-use loop). */
export const auth = {
  subtitle: 'Manage all your downloaders in one place',
  usernamePlaceholder: 'Username',
  passwordPlaceholder: 'Password',
  twofaPlaceholder: 'Two-factor code (required if enabled)',
  rememberMe: 'Remember me',
  forgotPassword: 'Forgot password?',
  loggingIn: 'Signing in...',
  login: 'Sign in',
  loginSuccess: 'Signed in successfully',
  loginFailed: 'Sign-in failed. Please try again.',
  enterDemo: 'Enter demo mode',
  demoEntered: 'Demo mode started',
  noAccount: "Don't have an account?",
  registerNow: 'Register now',
  tokenMissing: 'Your session is missing. Please sign in again.',
  /* Bilingual leftover fix: user store Login/GetUserInfo thrown messages */
  noAccessToken: 'Login failed: no access token was received',
  tokenEmpty: 'The token is empty. Please sign in again.',
  getUserInfoFailed: 'Failed to load user information',
  getUserInfoFailedRelogin: 'Failed to load user information. Please sign in again.',
  validation: {
    username: 'Enter a valid username',
    passwordMin: 'Password must be at least 5 characters',
    twofaDigits: 'Two-factor code must be 6 digits'
  }
}
