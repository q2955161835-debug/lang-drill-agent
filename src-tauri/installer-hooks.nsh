Function LangDrillValidateAsciiInstallDir
  Push $0
  Push $1
  Push $2
  Push $3
  Push $4

  StrLen $0 "$INSTDIR"
  StrCpy $1 0

  ${DoWhile} $1 < $0
    StrCpy $2 "$INSTDIR" 1 $1
    System::Call "*(&t1 r2) p .r3"
    !if "${NSIS_CHAR_SIZE}" > 1
      System::Call "*$3(&i2 .r4)"
    !else
      System::Call "*$3(&i1 .r4)"
    !endif
    System::Free $3

    ${If} $4 > 127
      ClearErrors
      RMDir "$INSTDIR"
      SetErrorLevel 1
      ${IfNot} ${Silent}
        MessageBox MB_ICONSTOP|MB_OK "The installation path must use English/ASCII characters only. Please choose a path such as C:\LangDrillAgent or D:\LangDrillAgent."
      ${EndIf}
      Pop $4
      Pop $3
      Pop $2
      Pop $1
      Pop $0
      Abort
    ${EndIf}

    IntOp $1 $1 + 1
  ${Loop}

  Pop $4
  Pop $3
  Pop $2
  Pop $1
  Pop $0
FunctionEnd

!macro NSIS_HOOK_PREINSTALL
  Call LangDrillValidateAsciiInstallDir
!macroend
