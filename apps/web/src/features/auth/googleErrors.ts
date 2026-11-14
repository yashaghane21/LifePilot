/** Messages for the `?error=` codes the Google callback sends back to /login. */
export const GOOGLE_ERROR_MESSAGES: Record<string, string> = {
  google_cancelled: 'Google sign-in was cancelled.',
  google_failed: 'Google sign-in didn’t complete. Please try again.',
  google_email_unverified: 'Your Google account’s email address isn’t verified, so it can’t be used to sign in.',
  account_disabled: 'This account has been disabled.',
}
