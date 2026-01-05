# Logout

```plantuml
@startuml
title Logout
autonumber
actor User
participant System

User -> System : Open account menu
User -> System : Confirm logout
System -> User : End session
System -> User : Clear local token
System -> User : Return to login screen
@enduml
```
