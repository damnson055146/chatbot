# Stop Streaming

```plantuml
@startuml
title Stop Streaming
autonumber
actor User
participant System

User -> System : Streaming in progress
User -> System : Click stop
System -> User : Abort streaming request
System -> User : Stop generation
@enduml
```
