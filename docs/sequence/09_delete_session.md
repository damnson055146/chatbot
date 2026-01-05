# Delete Session

```plantuml
@startuml
title Delete Session
autonumber
actor User
participant System

User -> System : Click delete
alt Confirm? Yes
  System -> User : Delete session using id
  System -> User : Remove from list
else No
  User -> System : Cancel delete
end
@enduml
```
