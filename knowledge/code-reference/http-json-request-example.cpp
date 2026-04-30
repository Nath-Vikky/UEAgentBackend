// Minimal HTTP JSON request reference for UE C++ code generation.
// Required Build.cs modules: HTTP, Json, JsonUtilities.

#include "HttpModule.h"
#include "Interfaces/IHttpRequest.h"
#include "Interfaces/IHttpResponse.h"

void SendExampleHttpRequest()
{
    FHttpRequestRef Request = FHttpModule::Get().CreateRequest();
    Request->SetURL(TEXT("https://api.example.com/v1/status"));
    Request->SetVerb(TEXT("GET"));
    Request->SetHeader(TEXT("Accept"), TEXT("application/json"));

    Request->OnProcessRequestComplete().BindLambda(
        [](FHttpRequestPtr RequestPtr, FHttpResponsePtr Response, bool bWasSuccessful)
        {
            if (!bWasSuccessful || !Response.IsValid())
            {
                UE_LOG(LogTemp, Warning, TEXT("HTTP request failed before a valid response was received."));
                return;
            }

            const int32 StatusCode = Response->GetResponseCode();
            const FString Body = Response->GetContentAsString();
            UE_LOG(LogTemp, Log, TEXT("HTTP %d: %s"), StatusCode, *Body);
        }
    );

    Request->ProcessRequest();
}

