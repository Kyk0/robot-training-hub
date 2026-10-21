# Participant accounts and email

Open the live app as admin → **Workshop settings → Email delivery**. Python's standard `smtplib` sends mail; no separate mail daemon is required. An actual sender account or approved SMTP relay is still required. The workstation has neither configured yet, so real delivery has not been verified.

For a Gmail sender, enter `smtp.gmail.com`, STARTTLS / 587 (or TLS / 465), your sender email, username, and a Google app password. Google requires 2-Step Verification for app passwords, and some accounts restrict their availability. See [Google's app-password instructions](https://support.google.com/mail/answer/185833) and [SMTP configuration](https://support.google.com/a/answer/176600). A Gmail sender can send invitations to participant university addresses. Enter the app password only into the app's HTTPS settings form; do not send it in chat.

1. Click **Verify & save email account**. This checks the encrypted connection and account login before saving.
2. Click **Send test email to me** and check your inbox/spam folder. The app reports mail-server acceptance, not proof of inbox delivery.
3. Under **Participants**, paste attendee emails, choose 1024 / 2048 / 4096 as their maximum, and use **Add & email passwords**. The add form generates passwords for the supplied accounts, including resetting existing accounts if they are supplied again.
4. The admin can see and copy newly generated passwords in **Generated passwords**. Dismissing or leaving the page clears that display. Password hashes are saved; the app cannot reveal an older saved password. Use **Reset & email password** to issue a new one.
5. If delivery fails, the result says so and the generated password remains visible for copying. Resetting revokes the participant's previous sessions and outstanding sign-in links. No failed send is presented as successful email.

Without a configured sender, **Add & generate passwords** and **Generate password** work for private manual distribution. Email buttons remain disabled. Development outbox results are explicitly labeled and do not count as sent mail.

SMTP credentials are stored only on the coordinator, in a mode-0600 `data/workshop/smtp.json`, excluded from Git and source snapshots. API responses expose configuration status but never the saved SMTP password. SMTP environment variables remain supported for operator-managed deployments; a saved settings file takes precedence.

**Delete participant** removes access and the participant-list entry, revokes sessions/password/sign-in links, cancels queued jobs and requests safe termination of admitted jobs. Running capacity stays reserved until the worker confirms termination. Historical run ownership and immutable artifacts remain for admins; this action is account removal, not deletion of research records. Re-adding that email restores the participant record, requiring fresh credentials.

All environment fields validate integer powers of two in the backend, including per-user, workshop, task and GPU limits. The workshop UI offers only 1024 / 2048 / 4096 and has no environment increment-by-one control.
