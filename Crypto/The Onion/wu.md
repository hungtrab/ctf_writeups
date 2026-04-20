## The Onion

Can you peel back the layers?

NOTE: The answer you get will not have the CIT{} wrapper, make sure you add it to the final answer.

### Attachment

- challenge.txt

### Story

challenge.txt contains a base64 code:

```
Vm0wd2QyUXlVWGxWV0d4V1YwZDRWMVl3WkRSWFJteFZVMjA1VjAxV2JETlhhMk0xVmpGYWMySkVUbGhoTVVwVVZtcEdTMk15U2tWVWJHaG9UVlZ3VlZadGNFSmxSbGw1VTJ0V1ZXSkhhRzlVVmxaM1ZsWmFkR05GZEZSTlZUVkpWbTEwVjFWdFNsWlhiRkpYWVd0d2RscFdXbUZrUjFaSFYyMTRVMkpIZHpGV2EyUXdZekpHYzFOdVVsWmhlbXhoVm1wT2IyRkdjRmRYYlVaclVsUkdWbFpYZUhkV01ERkZVbFJHVjJFeVVYZFpla3BIWXpGT...
```

After decode, it still give a base64 code but shorter -> kinda match with peeling the onion like in the title.

After 15 consecutive decode, the code remain:

```
b9486c74c779db5194d6508bebbee72b
```

This is a md5 code, now just need a solver. Using [crackstation](https://crackstation.net/) give:

```
iloveharrypottersomuchthaticouldreadallthebooksintwodaysmostlikely
```

### Final flag

```
CIT{iloveharrypottersomuchthaticouldreadallthebooksintwodaysmostlikely}
```
