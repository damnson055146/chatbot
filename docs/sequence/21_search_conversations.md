# Search Conversations

```plantuml
@startuml
title Search Conversations
autonumber
actor User
participant System

User -> System : Type search term
System -> User : Filter conversations in the app
System -> User : Show matching conversations
@enduml
```
