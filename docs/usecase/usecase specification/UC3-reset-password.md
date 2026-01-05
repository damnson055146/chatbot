# Use Case UC3 - Reset Password

Description
This use case enables a writer to reset their password and return to the sign-in page.

Actors
- Writer

Preconditions/Dependencies
1. UC2 - Sign In

Post Conditions
1. Password is reset.
2. Writer is redirected to sign-in page.

Standard Process
1. Writer clicks the "forget password" feature.
2. Application prompts writer to enter email.
3. Writer enters email.
4. Writer clicks "reset password" button.
5. Application checks if the email exists. If yes, proceed to next step.
6. Application gets the user ID of the email owner.
7. Application generates a reset token with an expiration period.
8. Application stores the reset token with user ID.
9. Application generates a link for writer to click to reset password.
10. Application sends the link to writer's email.
11. Writer clicks on the link.
12. Application redirects writer to reset password page.
13. Application prompts writer to enter new and confirm password.
14. Writer inputs the passwords.
15. Writer clicks "confirm" button.
16. Application checks if two passwords match. If yes, proceed to next step.
17. Application checks if token exists. If yes, proceed to next step.
18. Application checks if the password has minimum eight characters. If yes, proceed to next step.
19. Application updates the password.
20. Application displays message "Password is reset".
21. Application redirects writer to sign-in page.
