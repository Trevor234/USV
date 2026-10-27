#include <casadi/casadi.hpp>
int main(){casadi::Opti o; o.subject_to(o.x() >= 0); return 0;}
