#include <stdio.h>
#include <string.h>

int main(void) {
    char password[20];
    const char* correctPassword = "password123";

    printf("Enter the password: ");
    fgets(password, sizeof(password), stdin);

    // Remove the newline character from the input
    password[strcspn(password, "\n")] = '\0';

    if (strcmp(password, correctPassword) == 0) {
        printf("Password correct! Access granted.\n");
    } else {
        printf("Password incorrect! Access denied.\n");
    }

    return 0;
}