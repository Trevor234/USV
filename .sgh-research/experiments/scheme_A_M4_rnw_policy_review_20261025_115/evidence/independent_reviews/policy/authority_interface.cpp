#include "/home/trevor/USV/.sgh-research/experiments/scheme_A_M4_t2a_rnw2_impl_20261025_112/implementation/t2_author/observer/src/shadow/owned_execution_policy_native_v1.hpp"
#include <type_traits>
#include <utility>
#include <iostream>
template<class T,class=void>struct has_change_version:std::false_type{};
template<class T>struct has_change_version<T,std::void_t<decltype(std::declval<T&>().change_version(std::declval<const p1::Version&>(),int64_t{}))>>:std::true_type{};
static_assert(!has_change_version<p1::owned_execution::OutputAuthority>::value);
int main(){std::cout<<"actual OutputAuthority has_change_version=false\n";}
