# Rename Conversation

```plantuml
@startuml
title Rename Conversation
autonumber
actor User
participant System

User -> System : Open rename dialog
User -> System : Enter new title
System -> User : Update session title using id
System -> User : Update list title
@enduml
```
